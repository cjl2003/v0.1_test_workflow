#!/usr/bin/env python3
"""Manual PR fixer triggered by `/codex-fix` issue comments."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from reviewer import (
        DEFAULT_GITHUB_API_BASE,
        DEFAULT_GITHUB_API_VERSION,
        DEFAULT_MAX_OUTPUT_TOKENS,
        DEFAULT_OPENAI_API_BASE,
        DEFAULT_OPENAI_ENDPOINT_STYLE,
        DEFAULT_OPENAI_MODEL,
        DEFAULT_REASONING_EFFORT,
        GITHUB_COMMENT_SOFT_LIMIT,
        REQUEST_TIMEOUT_SECONDS,
        REVIEW_COMMENT_MARKER,
        ReviewerError,
        build_github_session,
        call_openai_review,
        fetch_pull_request,
        get_env,
        github_get_json,
        github_send_json,
        parse_positive_int,
        split_repo,
    )
except ImportError:
    from tools.reviewer import (
        DEFAULT_GITHUB_API_BASE,
        DEFAULT_GITHUB_API_VERSION,
        DEFAULT_MAX_OUTPUT_TOKENS,
        DEFAULT_OPENAI_API_BASE,
        DEFAULT_OPENAI_ENDPOINT_STYLE,
        DEFAULT_OPENAI_MODEL,
        DEFAULT_REASONING_EFFORT,
        GITHUB_COMMENT_SOFT_LIMIT,
        REQUEST_TIMEOUT_SECONDS,
        REVIEW_COMMENT_MARKER,
        ReviewerError,
        build_github_session,
        call_openai_review,
        fetch_pull_request,
        get_env,
        github_get_json,
        github_send_json,
        parse_positive_int,
        split_repo,
    )


FIX_COMMENT_MARKER = "<!-- rtl-auto-fix -->"
FIX_TRIGGER = "/codex-fix"
DEFAULT_VERIFY_COMMAND = "git diff --check"
DEFAULT_MAX_FIX_CONTEXT_CHARS = 90000
TEXT_FILE_SIZE_LIMIT = 100_000


@dataclass
class FixConfig:
    openai_api_key: str
    github_token: str
    github_repo: str
    pr_number: int
    comment_body: str
    openai_model: str
    openai_reasoning_effort: str
    openai_endpoint_style: str
    max_output_tokens: int
    github_api_base: str
    github_api_version: str
    openai_api_base: str
    verify_command: str
    max_fix_context_chars: int
    repo_root: Path
    dry_run: bool


@dataclass
class FileContext:
    path: str
    status: str
    patch: str
    content: str


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Apply a model-generated fix to the current PR branch."
    )
    parser.add_argument(
        "pr_number",
        nargs="?",
        help="Pull request number. Falls back to PR_NUMBER if omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write files, commit, push, or comment back to GitHub.",
    )
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> FixConfig:
    """Load runtime configuration from CLI args and environment variables."""
    load_dotenv()

    raw_pr_number = args.pr_number or get_env("PR_NUMBER", required=True)
    default_model = get_env("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    return FixConfig(
        openai_api_key=get_env("OPENAI_API_KEY", required=True),
        github_token=get_env("GITHUB_TOKEN", required=True),
        github_repo=get_env("GITHUB_REPO", required=True),
        pr_number=parse_positive_int(str(raw_pr_number), "PR_NUMBER"),
        comment_body=get_env("COMMENT_BODY", required=True),
        openai_model=get_env("OPENAI_FIX_MODEL", default_model),
        openai_reasoning_effort=get_env(
            "OPENAI_REASONING_EFFORT", DEFAULT_REASONING_EFFORT
        ),
        openai_endpoint_style=get_env(
            "OPENAI_ENDPOINT_STYLE", DEFAULT_OPENAI_ENDPOINT_STYLE
        ).lower(),
        max_output_tokens=parse_positive_int(
            get_env(
                "OPENAI_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS)
            ),
            "OPENAI_MAX_OUTPUT_TOKENS",
        ),
        github_api_base=get_env("GITHUB_API_BASE", DEFAULT_GITHUB_API_BASE).rstrip("/"),
        github_api_version=get_env(
            "GITHUB_API_VERSION", DEFAULT_GITHUB_API_VERSION
        ),
        openai_api_base=get_env("OPENAI_API_BASE", DEFAULT_OPENAI_API_BASE).rstrip("/"),
        verify_command=get_env("CODEX_FIX_VERIFY_COMMAND", DEFAULT_VERIFY_COMMAND),
        max_fix_context_chars=parse_positive_int(
            get_env(
                "MAX_FIX_CONTEXT_CHARS", str(DEFAULT_MAX_FIX_CONTEXT_CHARS)
            ),
            "MAX_FIX_CONTEXT_CHARS",
        ),
        repo_root=Path.cwd().resolve(),
        dry_run=args.dry_run,
    )


def parse_fix_command(comment_body: str) -> str:
    """Extract any user note attached to `/codex-fix`."""
    normalized = comment_body.strip()
    if not normalized.startswith(FIX_TRIGGER):
        raise ReviewerError(
            f"Comment does not start with {FIX_TRIGGER!r}: {comment_body!r}"
        )
    return normalized[len(FIX_TRIGGER) :].strip()


def resolve_repo_path(repo_root: Path, relative_path: str) -> Path:
    """Resolve a repo-relative path and block path traversal."""
    resolved = (repo_root / relative_path).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as error:
        raise ReviewerError(f"Path escapes repository root: {relative_path!r}") from error
    return resolved


def list_pull_request_files(
    session: Any, config: FixConfig, owner: str, repo: str
) -> list[dict[str, Any]]:
    """Fetch all changed files for the pull request."""
    results: list[dict[str, Any]] = []
    page = 1

    while True:
        url = (
            f"{config.github_api_base}/repos/{owner}/{repo}/pulls/"
            f"{config.pr_number}/files?per_page=100&page={page}"
        )
        payload = github_get_json(session, url, "Listing pull request files")
        if not isinstance(payload, list):
            raise ReviewerError("Unexpected GitHub pull request files payload format.")

        page_items = [item for item in payload if isinstance(item, dict)]
        results.extend(page_items)
        if len(payload) < 100:
            break
        page += 1

    return results


def build_file_contexts(
    repo_root: Path, pull_request_files: list[dict[str, Any]]
) -> list[FileContext]:
    """Collect editable text files from the checked-out PR branch."""
    contexts: list[FileContext] = []

    for item in pull_request_files:
        path = str(item.get("filename", "")).strip()
        status = str(item.get("status", "unknown"))
        if not path or status == "removed":
            continue

        resolved = resolve_repo_path(repo_root, path)
        if not resolved.exists() or not resolved.is_file():
            continue

        raw_bytes = resolved.read_bytes()
        if len(raw_bytes) > TEXT_FILE_SIZE_LIMIT:
            continue

        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            continue

        contexts.append(
            FileContext(
                path=path,
                status=status,
                patch=str(item.get("patch", "")).strip(),
                content=content,
            )
        )

    if not contexts:
        raise ReviewerError(
            "No editable UTF-8 text files were found in the checked-out PR branch."
        )

    return contexts


def find_existing_marked_comment(
    session: Any, config: FixConfig, owner: str, repo: str, marker: str
) -> dict[str, Any] | None:
    """Find the latest comment containing a marker string."""
    comments_url = (
        f"{config.github_api_base}/repos/{owner}/{repo}/issues/"
        f"{config.pr_number}/comments?per_page=100"
    )
    payload = github_get_json(session, comments_url, "Listing PR comments")
    if not isinstance(payload, list):
        raise ReviewerError("Unexpected GitHub comments payload format.")

    for comment in reversed(payload):
        if not isinstance(comment, dict):
            continue
        if marker in str(comment.get("body", "")):
            return comment
    return None


def upsert_marked_comment(
    session: Any,
    config: FixConfig,
    owner: str,
    repo: str,
    marker: str,
    body: str,
    context_label: str,
) -> tuple[str, str]:
    """Create or update a marked PR comment."""
    existing_comment = find_existing_marked_comment(session, config, owner, repo, marker)

    if existing_comment:
        comment_id = existing_comment.get("id")
        if not comment_id:
            raise ReviewerError("Existing marked comment is missing an id.")
        url = (
            f"{config.github_api_base}/repos/{owner}/{repo}/issues/comments/"
            f"{comment_id}"
        )
        result = github_send_json(
            session, "PATCH", url, {"body": body}, f"Updating {context_label} comment"
        )
        return "updated", str(result.get("html_url", url))

    url = (
        f"{config.github_api_base}/repos/{owner}/{repo}/issues/"
        f"{config.pr_number}/comments"
    )
    result = github_send_json(
        session, "POST", url, {"body": body}, f"Creating {context_label} comment"
    )
    return "created", str(result.get("html_url", url))


def build_fix_instructions(allowed_paths: list[str]) -> str:
    """Build the system instructions for the fixer model."""
    allowed_paths_block = "\n".join(f"- {path}" for path in allowed_paths)
    return textwrap.dedent(
        f"""
        You are Codex acting as a careful GitHub PR repair agent for RTL/Verilog work.
        Fix only the latest concrete issues from the existing auto-review comment.
        Keep edits minimal and safe.
        You may modify only these already-changed files:
        {allowed_paths_block}

        Output strict JSON only. Do not wrap it in Markdown fences.
        The JSON schema is:
        {{
          "summary": "Short Chinese summary of what you changed or why you declined.",
          "rationale": ["Short bullet-sized strings."],
          "edits": [
            {{
              "path": "relative/path/from/repo/root",
              "content": "full replacement file content"
            }}
          ]
        }}

        Rules:
        - Never create new files.
        - Never rename files.
        - Never edit files outside the allowed list.
        - Return complete file contents for each edited file.
        - Preserve unrelated logic and comments.
        - If the review comment requests verification or style cleanup that cannot be done safely,
          leave "edits" empty and explain the reason in "summary".
        """
    ).strip()


def prioritize_file_contexts(
    file_contexts: list[FileContext], review_comment: str
) -> list[FileContext]:
    """Prioritize files referenced by the review comment."""
    referenced = [ctx for ctx in file_contexts if ctx.path in review_comment]
    unreferenced = [ctx for ctx in file_contexts if ctx.path not in review_comment]
    return referenced + unreferenced


def build_fix_input(
    config: FixConfig,
    pull_request: dict[str, Any],
    review_comment: str,
    user_note: str,
    file_contexts: list[FileContext],
) -> str:
    """Build the model input with the review finding and local file contents."""
    title = str(pull_request.get("title") or "(no title)")
    body = str(pull_request.get("body") or "(no description)")
    pr_url = str(pull_request.get("html_url") or "(no url)")

    sections: list[str] = [
        f"Repository: {config.github_repo}",
        f"PR Number: #{config.pr_number}",
        f"PR URL: {pr_url}",
        f"Title: {title}",
        "PR Description:",
        body,
        "",
        "User Trigger:",
        user_note or "(no extra instruction)",
        "",
        "Latest Auto Review Comment:",
        review_comment,
        "",
        "Editable File Snapshots:",
    ]
    current_size = sum(len(section) for section in sections)

    for ctx in prioritize_file_contexts(file_contexts, review_comment):
        patch_block = ctx.patch or "(GitHub file patch unavailable)"
        block = textwrap.dedent(
            f"""
            --- FILE START: {ctx.path} ---
            Status: {ctx.status}
            PR Patch:
            {patch_block}

            Current Content:
            {ctx.content}
            --- FILE END: {ctx.path} ---
            """
        ).strip()
        if current_size + len(block) > config.max_fix_context_chars:
            break
        sections.extend(["", block])
        current_size += len(block)

    return "\n".join(sections).strip()


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating fenced wrappers."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ReviewerError(f"Model output did not contain a JSON object: {raw_text[:500]}")

    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise ReviewerError(
            f"Could not parse model JSON payload: {error}: {text[start:end + 1][:500]}"
        ) from error

    if not isinstance(payload, dict):
        raise ReviewerError("Model output JSON must be an object.")
    return payload


def normalize_fix_payload(
    payload: dict[str, Any], allowed_paths: set[str]
) -> tuple[str, list[str], list[dict[str, str]]]:
    """Validate the model payload and normalize edits."""
    summary = str(payload.get("summary", "")).strip()
    rationale_raw = payload.get("rationale", [])
    edits_raw = payload.get("edits", [])

    if not summary:
        raise ReviewerError("Model JSON payload is missing a non-empty summary.")
    if not isinstance(edits_raw, list):
        raise ReviewerError("Model JSON payload field 'edits' must be a list.")

    rationale: list[str] = []
    if isinstance(rationale_raw, list):
        for item in rationale_raw:
            text = str(item).strip()
            if text:
                rationale.append(text)

    edits: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    for item in edits_raw:
        if not isinstance(item, dict):
            raise ReviewerError("Each edit entry must be an object.")
        path = str(item.get("path", "")).strip()
        content = item.get("content", "")
        if path not in allowed_paths:
            raise ReviewerError(f"Model attempted to edit a disallowed file: {path!r}")
        if path in seen_paths:
            raise ReviewerError(f"Model returned duplicate edits for file: {path!r}")
        if not isinstance(content, str):
            raise ReviewerError(f"Model returned non-string content for file: {path!r}")
        seen_paths.add(path)
        edits.append({"path": path, "content": content})

    return summary, rationale, edits


def apply_model_edits(repo_root: Path, edits: list[dict[str, str]]) -> list[str]:
    """Write full-file replacements and report which files changed."""
    changed_paths: list[str] = []

    for edit in edits:
        path = edit["path"]
        content = edit["content"]
        resolved = resolve_repo_path(repo_root, path)
        original = resolved.read_text(encoding="utf-8")
        if original == content:
            continue
        resolved.write_text(content, encoding="utf-8")
        changed_paths.append(path)

    return changed_paths


def run_shell_command(command: str, cwd: Path) -> tuple[int, str]:
    """Run a shell command and capture combined stdout/stderr."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        check=False,
        text=True,
        capture_output=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode, output


def run_git_command(args: list[str], cwd: Path) -> str:
    """Run a git command and raise a ReviewerError on failure."""
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr).strip()
        raise ReviewerError(f"Git command failed: {' '.join(args)}: {output}")
    return (completed.stdout + completed.stderr).strip()


def commit_and_push_changes(
    repo_root: Path, changed_paths: list[str], pr_number: int
) -> tuple[str, str]:
    """Commit staged changes and push them back to the current branch."""
    branch_name = run_git_command(["git", "branch", "--show-current"], repo_root).strip()
    if not branch_name:
        raise ReviewerError("The workflow is on a detached HEAD and cannot push a fix branch.")

    run_git_command(["git", "add", "--", *changed_paths], repo_root)
    run_git_command(
        ["git", "commit", "-m", f"fix: apply Codex fixes for PR #{pr_number}"],
        repo_root,
    )
    commit_sha = run_git_command(["git", "rev-parse", "HEAD"], repo_root).strip()
    run_git_command(["git", "push", "origin", branch_name], repo_root)
    return branch_name, commit_sha


def format_fix_comment_body(
    config: FixConfig,
    status: str,
    summary: str,
    rationale: list[str] | None = None,
    changed_paths: list[str] | None = None,
    verify_output: str | None = None,
    commit_sha: str | None = None,
    response_id: str | None = None,
    error_message: str | None = None,
) -> str:
    """Build a single updatable PR comment for the fix workflow."""
    lines = [
        FIX_COMMENT_MARKER,
        "## RTL Auto Fix",
        f"- PR: `#{config.pr_number}`",
        f"- Trigger: `{FIX_TRIGGER}`",
        f"- Model: `{config.openai_model}`",
        f"- Status: `{status}`",
    ]
    if response_id:
        lines.append(f"- Model response id: `{response_id}`")
    if commit_sha:
        lines.append(f"- Fix commit: `{commit_sha}`")
    if changed_paths:
        lines.append(f"- Updated files: `{', '.join(changed_paths)}`")
    lines.extend(["", summary.strip() or "(no summary)"])

    if rationale:
        lines.extend(["", "### Rationale", *[f"- {item}" for item in rationale]])

    if verify_output is not None:
        compact_output = verify_output.strip() or "(no output)"
        if len(compact_output) > 1500:
            compact_output = compact_output[:1500].rstrip() + "..."
        lines.extend(
            [
                "",
                "### Verification",
                f"- Command: `{config.verify_command}`",
                "```text",
                compact_output,
                "```",
            ]
        )

    if status == "success":
        lines.extend(
            [
                "",
                "现有 `auto-review.yml` 会因为这次推送自动再次运行，生成新的 RTL 审核结果。",
            ]
        )

    if error_message:
        compact_error = " ".join(error_message.strip().split())
        if len(compact_error) > 1500:
            compact_error = compact_error[:1500].rstrip() + "..."
        lines.extend(["", f"- Failure reason: `{compact_error}`"])

    body = "\n".join(lines).strip()
    if len(body) <= GITHUB_COMMENT_SOFT_LIMIT:
        return body
    return body[: GITHUB_COMMENT_SOFT_LIMIT - 60].rstrip() + "\n\n_(truncated)_"


def main() -> int:
    """Entry point used by GitHub Actions and local dry runs."""
    args = parse_args()
    config = load_config(args)
    owner, repo = split_repo(config.github_repo)
    user_note = parse_fix_command(config.comment_body)

    print(f"[codex-fix] Repo: {config.github_repo}")
    print(f"[codex-fix] PR: #{config.pr_number}")
    print(f"[codex-fix] Model: {config.openai_model}")

    with build_github_session(config) as github_session:
        try:
            pull_request = fetch_pull_request(github_session, config, owner, repo)
            if str(pull_request.get("state", "")).lower() != "open":
                raise ReviewerError("The pull request is not open.")

            head_repo = (
                ((pull_request.get("head") or {}).get("repo") or {}).get("full_name")
                or ""
            )
            if head_repo != config.github_repo:
                raise ReviewerError(
                    "Cross-repository PRs are not supported by the minimal auto-fix workflow."
                )

            review_comment = find_existing_marked_comment(
                github_session, config, owner, repo, REVIEW_COMMENT_MARKER
            )
            if not review_comment:
                raise ReviewerError("No existing RTL auto-review comment was found on the PR.")

            running_comment = format_fix_comment_body(
                config,
                status="running",
                summary="正在读取最新审核意见并尝试生成最小修复。",
            )
            if not config.dry_run:
                action, comment_url = upsert_marked_comment(
                    github_session,
                    config,
                    owner,
                    repo,
                    FIX_COMMENT_MARKER,
                    running_comment,
                    "auto-fix",
                )
                print(f"[codex-fix] Successfully {action} PR comment: {comment_url}")

            pull_request_files = list_pull_request_files(
                github_session, config, owner, repo
            )
            file_contexts = build_file_contexts(config.repo_root, pull_request_files)
            allowed_paths = {ctx.path for ctx in file_contexts}

            instructions = build_fix_instructions(sorted(allowed_paths))
            model_input = build_fix_input(
                config,
                pull_request,
                str(review_comment.get("body", "")),
                user_note,
                file_contexts,
            )
            raw_fix_text, response_id = call_openai_review(
                config, instructions, model_input
            )
            payload = extract_json_payload(raw_fix_text)
            summary, rationale, edits = normalize_fix_payload(payload, allowed_paths)

            if config.dry_run:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                print(
                    "[codex-fix] Dry run complete. No files, commits, pushes, or comments."
                )
                return 0

            changed_paths = apply_model_edits(config.repo_root, edits)
            if not changed_paths:
                noop_comment = format_fix_comment_body(
                    config,
                    status="no_changes",
                    summary=summary,
                    rationale=rationale,
                    response_id=response_id,
                )
                action, comment_url = upsert_marked_comment(
                    github_session,
                    config,
                    owner,
                    repo,
                    FIX_COMMENT_MARKER,
                    noop_comment,
                    "auto-fix",
                )
                print(f"[codex-fix] Successfully {action} PR comment: {comment_url}")
                return 0

            verify_exit_code, verify_output = run_shell_command(
                config.verify_command, config.repo_root
            )
            if verify_exit_code != 0:
                failure_comment = format_fix_comment_body(
                    config,
                    status="failed",
                    summary="自动修复已生成改动，但最小验证未通过，因此未推送到 PR 分支。",
                    rationale=rationale,
                    changed_paths=changed_paths,
                    verify_output=verify_output,
                    response_id=response_id,
                    error_message=f"Verification command failed with exit code {verify_exit_code}.",
                )
                action, comment_url = upsert_marked_comment(
                    github_session,
                    config,
                    owner,
                    repo,
                    FIX_COMMENT_MARKER,
                    failure_comment,
                    "auto-fix",
                )
                print(f"[codex-fix] Successfully {action} PR comment: {comment_url}")
                return 1

            branch_name, commit_sha = commit_and_push_changes(
                config.repo_root, changed_paths, config.pr_number
            )
            success_comment = format_fix_comment_body(
                config,
                status="success",
                summary=summary,
                rationale=rationale,
                changed_paths=changed_paths,
                verify_output=verify_output,
                commit_sha=commit_sha,
                response_id=response_id,
            )
            action, comment_url = upsert_marked_comment(
                github_session,
                config,
                owner,
                repo,
                FIX_COMMENT_MARKER,
                success_comment,
                "auto-fix",
            )
            print(f"[codex-fix] Successfully {action} PR comment: {comment_url}")
            print(f"[codex-fix] Pushed fix commit {commit_sha} to {branch_name}.")
        except Exception as error:
            if not config.dry_run:
                failure_comment = format_fix_comment_body(
                    config,
                    status="failed",
                    summary="自动修复流程未完成，未向 PR 分支推送新的修复提交。",
                    error_message=str(error),
                )
                try:
                    action, comment_url = upsert_marked_comment(
                        github_session,
                        config,
                        owner,
                        repo,
                        FIX_COMMENT_MARKER,
                        failure_comment,
                        "auto-fix",
                    )
                    print(f"[codex-fix] Successfully {action} PR comment: {comment_url}")
                except Exception as comment_error:
                    print(
                        f"[codex-fix] Failed to report auto-fix error back to GitHub: {comment_error}",
                        file=sys.stderr,
                    )
            raise

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReviewerError as error:
        print(f"[codex-fix] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    except subprocess.TimeoutExpired as error:
        print(f"[codex-fix] Command timed out: {error}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("[codex-fix] Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
