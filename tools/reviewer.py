#!/usr/bin/env python3
"""Minimal PR auto-reviewer for RTL/Verilog pull requests.

This script fetches a pull request diff from GitHub, sends it to the OpenAI
Responses API for review, and posts the review back as a PR comment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


REVIEW_COMMENT_MARKER = "<!-- rtl-auto-review -->"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_OPENAI_ENDPOINT_STYLE = "auto"
DEFAULT_MAX_DIFF_CHARS = 120000
DEFAULT_MAX_OUTPUT_TOKENS = 1800
DEFAULT_GITHUB_API_BASE = "https://api.github.com"
DEFAULT_OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_GITHUB_API_VERSION = "2022-11-28"
REQUEST_TIMEOUT_SECONDS = 60
GITHUB_COMMENT_SOFT_LIMIT = 60000
RULES_PATH = Path(__file__).resolve().parents[1] / ".ai" / "reviewer_rules.md"


class ReviewerError(RuntimeError):
    """Raised when the reviewer cannot complete its work safely."""


@dataclass
class Config:
    openai_api_key: str
    github_token: str
    github_repo: str
    pr_number: int
    openai_model: str
    openai_reasoning_effort: str
    openai_endpoint_style: str
    max_diff_chars: int
    max_output_tokens: int
    github_api_base: str
    github_api_version: str
    openai_api_base: str
    dry_run: bool


def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    """Read an environment variable and treat empty strings as missing.

    GitHub Actions passes missing repository variables as empty strings. For
    optional inputs we want blank values to fall back to the in-code defaults
    instead of overriding them with "".
    """
    value = os.getenv(name)
    if value is not None:
        value = value.strip()
        if value != "":
            return value

    if required:
        raise ReviewerError(f"Missing required environment variable: {name}")

    if default is None:
        return ""

    return default.strip()


def parse_positive_int(raw_value: str, env_name: str) -> int:
    """Validate integer-like environment values early with a helpful error."""
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ReviewerError(f"{env_name} must be an integer, got: {raw_value!r}") from error

    if value <= 0:
        raise ReviewerError(f"{env_name} must be greater than zero, got: {value}")

    return value


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    The PR number is positional to keep the GitHub Actions step simple.
    """
    parser = argparse.ArgumentParser(
        description="Fetch a PR diff, ask OpenAI for an RTL review, and comment on the PR."
    )
    parser.add_argument(
        "pr_number",
        nargs="?",
        help="Pull request number. Falls back to PR_NUMBER if omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated review instead of creating/updating a GitHub comment.",
    )
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> Config:
    """Load runtime configuration from the environment and CLI args."""
    load_dotenv()

    raw_pr_number = args.pr_number or get_env("PR_NUMBER", required=True)
    return Config(
        openai_api_key=get_env("OPENAI_API_KEY", required=True),
        github_token=get_env("GITHUB_TOKEN", required=True),
        github_repo=get_env("GITHUB_REPO", required=True),
        pr_number=parse_positive_int(str(raw_pr_number), "PR_NUMBER"),
        openai_model=get_env("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        openai_reasoning_effort=get_env(
            "OPENAI_REASONING_EFFORT", DEFAULT_REASONING_EFFORT
        ),
        openai_endpoint_style=get_env(
            "OPENAI_ENDPOINT_STYLE", DEFAULT_OPENAI_ENDPOINT_STYLE
        ).lower(),
        max_diff_chars=parse_positive_int(
            get_env("MAX_DIFF_CHARS", str(DEFAULT_MAX_DIFF_CHARS)), "MAX_DIFF_CHARS"
        ),
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
        dry_run=args.dry_run,
    )


def split_repo(full_repo: str) -> tuple[str, str]:
    """Split owner/repo and fail fast if the format is wrong."""
    if "/" not in full_repo:
        raise ReviewerError(
            "GITHUB_REPO must look like 'owner/repo', got: "
            f"{full_repo!r}"
        )

    owner, repo = full_repo.split("/", 1)
    if not owner or not repo:
        raise ReviewerError(
            "GITHUB_REPO must look like 'owner/repo', got: "
            f"{full_repo!r}"
        )
    return owner, repo


def build_github_session(config: Config) -> requests.Session:
    """Create a GitHub API session with standard headers."""
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {config.github_token}",
            "User-Agent": "rtl-auto-reviewer/1.0",
            "X-GitHub-Api-Version": config.github_api_version,
        }
    )
    return session


def raise_for_status(response: requests.Response, context: str) -> None:
    """Wrap HTTP failures with the body for easier debugging in Actions logs."""
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        body = response.text.strip()
        snippet = body[:1000] if body else "<empty response>"
        raise ReviewerError(
            f"{context} failed with HTTP {response.status_code}: {snippet}"
        ) from error


def github_get_json(session: requests.Session, url: str, context: str) -> Any:
    """Read JSON from the GitHub REST API."""
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    raise_for_status(response, context)
    return response.json()


def github_send_json(
    session: requests.Session,
    method: str,
    url: str,
    payload: dict[str, Any],
    context: str,
) -> Any:
    """Send JSON to the GitHub REST API."""
    response = session.request(
        method=method,
        url=url,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, context)
    return response.json()


def fetch_pull_request(
    session: requests.Session, config: Config, owner: str, repo: str
) -> dict[str, Any]:
    """Fetch pull request metadata used in the review prompt."""
    pr_url = (
        f"{config.github_api_base}/repos/{owner}/{repo}/pulls/{config.pr_number}"
    )
    payload = github_get_json(session, pr_url, "Fetching pull request metadata")
    if not isinstance(payload, dict):
        raise ReviewerError("Unexpected GitHub PR payload format.")
    return payload


def fetch_pull_request_diff(
    session: requests.Session, config: Config, owner: str, repo: str
) -> str:
    """Fetch the unified diff for the pull request."""
    pr_url = (
        f"{config.github_api_base}/repos/{owner}/{repo}/pulls/{config.pr_number}"
    )
    response = session.get(
        pr_url,
        headers={"Accept": "application/vnd.github.diff"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, "Fetching pull request diff")
    return response.text


def read_rules() -> str:
    """Load the RTL-specific review rubric from disk."""
    if not RULES_PATH.exists():
        raise ReviewerError(f"Review rules file not found: {RULES_PATH}")
    return RULES_PATH.read_text(encoding="utf-8").strip()


def truncate_diff(diff_text: str, max_chars: int) -> tuple[str, bool]:
    """Trim very large diffs while preserving both head and tail context."""
    if len(diff_text) <= max_chars:
        return diff_text, False

    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars
    trimmed = (
        diff_text[:head_chars]
        + "\n\n... [diff truncated by reviewer.py to stay within model context] ...\n\n"
        + diff_text[-tail_chars:]
    )
    return trimmed, True


def build_openai_instructions(rules_text: str) -> str:
    """Create the high-priority reviewer instructions for the model."""
    return textwrap.dedent(
        f"""
        You are a senior RTL/Verilog code reviewer working on a GitHub pull request.
        Focus on correctness, behavioral regressions, synthesis safety, and missing verification.
        Ignore style-only suggestions unless they hide a real bug or reviewability risk.
        If a concern is plausible but not certain, label it as a risk and explain why.
        Write the final review in Chinese using GitHub-flavored Markdown.
        Follow the repository-specific rules below.

        {rules_text}
        """
    ).strip()


def build_openai_input(
    config: Config,
    pull_request: dict[str, Any],
    diff_text: str,
    diff_truncated: bool,
) -> str:
    """Build the user-facing prompt with concrete PR context and diff content."""
    title = pull_request.get("title") or "(no title)"
    body = pull_request.get("body") or "(no description)"
    author = (pull_request.get("user") or {}).get("login") or "unknown"
    pr_url = pull_request.get("html_url") or "(no url)"
    base_ref = ((pull_request.get("base") or {}).get("ref")) or "unknown"
    head_ref = ((pull_request.get("head") or {}).get("ref")) or "unknown"
    changed_files = pull_request.get("changed_files", "unknown")
    additions = pull_request.get("additions", "unknown")
    deletions = pull_request.get("deletions", "unknown")

    truncation_note = (
        f"Yes. Only the first/last {config.max_diff_chars // 2} characters were kept."
        if diff_truncated
        else "No. The full diff is included."
    )

    return textwrap.dedent(
        f"""
        Please review the following GitHub pull request for RTL/Verilog/SystemVerilog risks.

        Repository: {config.github_repo}
        PR Number: #{config.pr_number}
        PR URL: {pr_url}
        Title: {title}
        Author: {author}
        Base Branch: {base_ref}
        Head Branch: {head_ref}
        Changed Files: {changed_files}
        Additions: {additions}
        Deletions: {deletions}
        Diff Truncated: {truncation_note}

        PR Description:
        {body}

        Unified Diff:
        {diff_text or "(GitHub returned an empty diff body.)"}
        """
    ).strip()


def call_openai_review(
    config: Config, instructions: str, review_input: str
) -> tuple[str, str]:
    """Send the diff to an OpenAI-compatible API and return the textual review."""
    endpoint_style = config.openai_endpoint_style
    if endpoint_style == "responses":
        return call_openai_responses_review(config, instructions, review_input)
    if endpoint_style == "chat_completions":
        return call_openai_chat_completions_review(config, instructions, review_input)
    if endpoint_style != "auto":
        raise ReviewerError(
            "OPENAI_ENDPOINT_STYLE must be one of: auto, responses, chat_completions"
        )

    try:
        return call_openai_responses_review(config, instructions, review_input)
    except ReviewerError as error:
        if not should_fallback_to_chat_completions(str(error)):
            raise
        print(
            "[reviewer] Responses API is unavailable on this endpoint. "
            "Falling back to chat completions."
        )
        return call_openai_chat_completions_review(config, instructions, review_input)


def call_openai_responses_review(
    config: Config, instructions: str, review_input: str
) -> tuple[str, str]:
    """Send the diff to OpenAI Responses API and return the textual review."""
    payload: dict[str, Any] = {
        "model": config.openai_model,
        "instructions": instructions,
        "input": review_input,
        "max_output_tokens": config.max_output_tokens,
        "metadata": {
            "tool": "rtl-pr-auto-reviewer",
            "repo": config.github_repo,
            "pr_number": str(config.pr_number),
        },
    }

    if config.openai_reasoning_effort:
        payload["reasoning"] = {"effort": config.openai_reasoning_effort}

    response = requests.post(
        f"{config.openai_api_base}/responses",
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, "Calling OpenAI Responses API")

    data = response.json()
    if not isinstance(data, dict):
        raise ReviewerError("Unexpected OpenAI response format.")

    review_text = extract_openai_text(data)
    response_id = str(data.get("id", "unknown"))
    if not review_text:
        raise ReviewerError(
            "OpenAI returned no output_text content. Raw payload: "
            f"{json.dumps(data)[:1500]}"
        )
    return review_text, response_id


def call_openai_chat_completions_review(
    config: Config, instructions: str, review_input: str
) -> tuple[str, str]:
    """Call an OpenAI-compatible chat completions endpoint."""
    payload: dict[str, Any] = {
        "model": config.openai_model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": review_input},
        ],
        "max_tokens": config.max_output_tokens,
    }

    response = requests.post(
        f"{config.openai_api_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, "Calling OpenAI-compatible chat completions API")

    data = response.json()
    if not isinstance(data, dict):
        raise ReviewerError("Unexpected chat completions response format.")

    review_text = extract_chat_completions_text(data)
    response_id = str(data.get("id", "unknown"))
    if not review_text:
        raise ReviewerError(
            "Chat completions API returned no review text. Raw payload: "
            f"{json.dumps(data)[:1500]}"
        )
    return review_text, response_id


def extract_openai_text(response_json: dict[str, Any]) -> str:
    """Aggregate all output_text chunks from a raw Responses API payload.

    The REST API returns text inside the `output` array rather than exposing the
    SDK-only `output_text` convenience property.
    """
    parts: list[str] = []

    for item in response_json.get("output", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") != "output_text":
                continue
            text = str(content.get("text", "")).strip()
            if text:
                parts.append(text)

    return "\n\n".join(parts).strip()


def extract_chat_completions_text(response_json: dict[str, Any]) -> str:
    """Extract assistant text from a chat completions-style response."""
    choices = response_json.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""

    message = (choices[0] or {}).get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in {"text", "output_text"}:
                continue
            text = str(item.get("text", "")).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    return ""


def should_fallback_to_chat_completions(error_message: str) -> bool:
    """Detect endpoint-shape failures that merit a chat completions retry."""
    retry_markers = ("HTTP 400", "HTTP 404", "HTTP 405", "HTTP 415", "HTTP 422")
    unsupported_markers = (
        "unsupported",
        "not found",
        "unknown url",
        "no route",
        "does not exist",
    )
    normalized = error_message.lower()
    return any(marker in error_message for marker in retry_markers) or any(
        marker in normalized for marker in unsupported_markers
    )


def format_comment_body(
    config: Config,
    review_text: str,
    diff_truncated: bool,
    response_id: str,
) -> str:
    """Build a single updatable PR comment body."""
    metadata_lines = [
        REVIEW_COMMENT_MARKER,
        "## RTL Auto Review",
        f"- PR: `#{config.pr_number}`",
        f"- Model: `{config.openai_model}`",
        f"- Endpoint style: `{config.openai_endpoint_style}`",
        f"- Reasoning effort: `{config.openai_reasoning_effort}`",
        f"- Diff coverage: `{'truncated' if diff_truncated else 'full'}`",
        f"- OpenAI response id: `{response_id}`",
        "",
        review_text.strip(),
    ]
    body = "\n".join(metadata_lines).strip()

    if len(body) <= GITHUB_COMMENT_SOFT_LIMIT:
        return body

    truncated_review = review_text[: GITHUB_COMMENT_SOFT_LIMIT - 800].rstrip()
    return "\n".join(
        [
            REVIEW_COMMENT_MARKER,
            "## RTL Auto Review",
            f"- PR: `#{config.pr_number}`",
            f"- Model: `{config.openai_model}`",
            f"- Endpoint style: `{config.openai_endpoint_style}`",
            "",
            truncated_review,
            "",
            "_Comment truncated by reviewer.py to stay within GitHub comment limits._",
        ]
    ).strip()


def format_failure_comment_body(config: Config, error_message: str) -> str:
    """Build a PR comment for reviewer failures that happen after trigger."""
    compact_error = " ".join(error_message.strip().split())
    if len(compact_error) > 1500:
        compact_error = compact_error[:1500].rstrip() + "..."

    return "\n".join(
        [
            REVIEW_COMMENT_MARKER,
            "## RTL Auto Review",
            f"- PR: `#{config.pr_number}`",
            f"- Model: `{config.openai_model}`",
            f"- Endpoint style: `{config.openai_endpoint_style}`",
            "- Status: `failed`",
            "",
            "自动审核已被触发，但本次没有产出审查结果。",
            "",
            f"- 失败原因：`{compact_error}`",
            "- 建议处理：检查 `OPENAI_API_KEY` 是否可用、额度是否充足，以及模型访问权限是否正常。",
        ]
    ).strip()


def find_existing_comment(
    session: requests.Session, config: Config, owner: str, repo: str
) -> dict[str, Any] | None:
    """Look for a previous auto-review comment so synchronize events update it."""
    comments_url = (
        f"{config.github_api_base}/repos/{owner}/{repo}/issues/"
        f"{config.pr_number}/comments"
    )
    payload = github_get_json(
        session, comments_url + "?per_page=100", "Listing existing PR comments"
    )
    if not isinstance(payload, list):
        raise ReviewerError("Unexpected GitHub comments payload format.")

    for comment in reversed(payload):
        if not isinstance(comment, dict):
            continue
        if REVIEW_COMMENT_MARKER in str(comment.get("body", "")):
            return comment
    return None


def upsert_comment(
    session: requests.Session,
    config: Config,
    owner: str,
    repo: str,
    comment_body: str,
) -> tuple[str, str]:
    """Create a new PR comment or update the previous auto-review comment."""
    existing_comment = find_existing_comment(session, config, owner, repo)

    if existing_comment:
        comment_id = existing_comment.get("id")
        if not comment_id:
            raise ReviewerError("Existing review comment is missing an id.")

        url = (
            f"{config.github_api_base}/repos/{owner}/{repo}/issues/comments/"
            f"{comment_id}"
        )
        result = github_send_json(
            session,
            "PATCH",
            url,
            {"body": comment_body},
            "Updating PR review comment",
        )
        return "updated", str(result.get("html_url", url))

    url = (
        f"{config.github_api_base}/repos/{owner}/{repo}/issues/"
        f"{config.pr_number}/comments"
    )
    result = github_send_json(
        session,
        "POST",
        url,
        {"body": comment_body},
        "Creating PR review comment",
    )
    return "created", str(result.get("html_url", url))


def main() -> int:
    """Entry point used by both GitHub Actions and local dry runs."""
    args = parse_args()
    config = load_config(args)
    owner, repo = split_repo(config.github_repo)
    rules_text = read_rules()

    print(f"[reviewer] Repo: {config.github_repo}")
    print(f"[reviewer] PR: #{config.pr_number}")
    print(f"[reviewer] Model: {config.openai_model}")

    with build_github_session(config) as github_session:
        pull_request = fetch_pull_request(github_session, config, owner, repo)
        raw_diff = fetch_pull_request_diff(github_session, config, owner, repo)
        review_diff, diff_truncated = truncate_diff(raw_diff, config.max_diff_chars)

        instructions = build_openai_instructions(rules_text)
        review_input = build_openai_input(
            config, pull_request, review_diff, diff_truncated
        )
        review_failed = False
        try:
            review_text, response_id = call_openai_review(
                config, instructions, review_input
            )
            comment_body = format_comment_body(
                config, review_text, diff_truncated, response_id
            )
        except ReviewerError as error:
            if config.dry_run:
                raise
            review_failed = True
            comment_body = format_failure_comment_body(config, str(error))

        if config.dry_run:
            print(comment_body)
            print("[reviewer] Dry run complete. No GitHub comment was created.")
            return 0

        action, comment_url = upsert_comment(
            github_session, config, owner, repo, comment_body
        )
        print(f"[reviewer] Successfully {action} PR comment: {comment_url}")
        if review_failed:
            print(
                "[reviewer] Review failed after posting status comment.",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReviewerError as error:
        print(f"[reviewer] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    except requests.RequestException as error:
        print(f"[reviewer] Network error: {error}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("[reviewer] Interrupted by user.", file=sys.stderr)
        raise SystemExit(130)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
