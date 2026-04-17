#!/usr/bin/env python3
"""Helpers and main entry point for the local phase-1 runner pickup flow."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.workflow_lib import (
    GitHubConfig,
    GitHubClient,
    MARKER_CODEX_RUN,
    MARKER_GPT_REVIEW,
    MARKER_PLAN,
    WorkflowError,
    comment_timestamp,
    extract_primary_state,
    find_latest_command_comment,
    find_latest_marker_comment,
    get_env,
    read_text_file,
    render_marked_comment,
    parse_timestamp,
)


REQUEST_FIELDS = {
    "Request Id": "request_id",
    "Title": "title",
    "Stage": "stage",
    "Base Branch": "base_branch",
    "Work Branch": "work_branch",
    "Version": "version",
}

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_STATE_ROOT = Path.home() / ".codex-phase1-runner"
LOCK_PATH = LOCAL_STATE_ROOT / "runner.lock"
WORKTREE_ROOT = LOCAL_STATE_ROOT / "worktrees"
LOG_ROOT = LOCAL_STATE_ROOT / "logs"
RUNS_ROOT = REPO_ROOT / "docs" / "runs"


@dataclass(frozen=True)
class QueueCandidate:
    pr_number: int
    queue_time: str
    execution_mode: str
    request_path: str
    plan_comment: dict[str, Any]
    review_comment: dict[str, Any] | None
    approve_plan_comment: dict[str, Any]
    codex_fix_comment: dict[str, Any] | None
    head_branch: str
    same_repo: bool


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


def parse_request_metadata(request_doc: str) -> dict[str, str]:
    """Extract required top-level request fields from the markdown document."""
    metadata: dict[str, str] = {}
    for label, key in REQUEST_FIELDS.items():
        pattern = re.compile(rf"^- {re.escape(label)}:\s+`(.+?)`\s*$", re.MULTILINE)
        match = pattern.search(request_doc)
        if not match:
            raise WorkflowError(f"Request document is missing required field: {label}")
        metadata[key] = match.group(1).strip()
    return metadata


def select_execution_mode(
    latest_plan_at: str,
    latest_approve_plan_at: str,
    latest_gpt_review_at: str | None,
    latest_codex_fix_at: str | None,
) -> str:
    """Choose the current execution round source according to the spec."""
    if parse_timestamp(latest_approve_plan_at) <= parse_timestamp(latest_plan_at):
        raise WorkflowError("A valid /approve-plan newer than the latest wf:plan is required.")

    if latest_gpt_review_at and latest_codex_fix_at:
        if parse_timestamp(latest_codex_fix_at) > parse_timestamp(latest_gpt_review_at):
            return "rework"

    return "plan"


def build_success_tag(timestamp_token: str, version: str) -> str:
    """Build the phase-1 success tag using the spec format."""
    return f"v0.1_frontend_pass_{timestamp_token}_{version}"


def render_run_result_document(
    request_id: str,
    run_id: str,
    version: str,
    tag: str,
    commands_executed: list[str],
    verification_summary: list[str],
    artifact_paths: list[str],
    notes: str,
) -> str:
    """Render the repository run result document."""
    return (
        f"# Frontend Run Result\n\n"
        f"- Request Id: `{request_id}`\n"
        f"- Run Id: `{run_id}`\n"
        f"- Version: `{version}`\n"
        f"- Status: `success`\n"
        f"- Tag: `{tag}`\n"
        f"- Commit: `pending`\n\n"
        f"## Commands Executed\n"
        + "\n".join(f"- `{item}`" for item in commands_executed)
        + "\n\n## Verification Summary\n"
        + "\n".join(f"- {item}" for item in verification_summary)
        + "\n\n## Artifact Paths\n"
        + "\n".join(f"- `{item}`" for item in artifact_paths)
        + f"\n\n## Short Notes\n{notes.strip()}\n"
    )


def render_codex_run_comment(
    status: str,
    run_id: str,
    verification_summary: list[str],
    run_result_path: str | None,
    commit_id: str | None,
    tag: str | None,
    failure_step: str | None,
    notes: str,
) -> str:
    """Render the machine-readable wf:codex-run comment."""
    metadata = [("Status", status), ("Run Id", run_id)]
    if commit_id:
        metadata.append(("Commit", commit_id))
    if tag:
        metadata.append(("Tag", tag))
    if failure_step:
        metadata.append(("Failure Step", failure_step))
    if run_result_path:
        metadata.append(("Run Result Path", run_result_path))

    sections: list[tuple[str, list[str] | str]] = [
        ("Verification Summary", verification_summary or ["No verification summary."]),
        ("Notes", notes.strip()),
    ]
    return render_marked_comment(
        MARKER_CODEX_RUN,
        "Local Codex Run",
        metadata,
        sections,
    )


def parse_repo_from_remote(remote_url: str) -> str:
    """Extract owner/repo from the repository origin URL."""
    remote = remote_url.strip()
    ssh_match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", remote)
    if ssh_match:
        return ssh_match.group(1)

    https_match = re.match(r"https://github\.com/(.+?)(?:\.git)?$", remote)
    if https_match:
        return https_match.group(1)

    raise WorkflowError(f"Unsupported origin URL for GitHub repo detection: {remote}")


def run_git(args: list[str], cwd: Path = REPO_ROOT) -> str:
    """Run a git command and return stdout."""
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise WorkflowError(
            f"git {' '.join(args)} failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout.strip()


def ensure_local_dirs() -> None:
    """Create local state directories used by the runner."""
    for path in (LOCAL_STATE_ROOT, WORKTREE_ROOT, LOG_ROOT, RUNS_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def format_timestamp_token(moment: datetime | None = None) -> str:
    """Build the shared timestamp token used in run ids, file names, and tags."""
    moment = moment or datetime.now(timezone.utc)
    return moment.strftime("%Y%m%d_%H%M%S")


def build_run_id(timestamp_token: str, version: str) -> str:
    """Build a stable run id for a phase-1 execution."""
    return f"run-{timestamp_token}-{version}"


def pid_is_running(pid: int) -> bool:
    """Check whether a process id is still alive on the local machine."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_lock_data() -> dict[str, Any] | None:
    """Read the local runner lock file when it exists."""
    if not LOCK_PATH.exists():
        return None
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def write_lock_data(pr_number: int, run_id: str, worktree_path: Path) -> None:
    """Persist the single-runner lock."""
    LOCK_PATH.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "pr_number": pr_number,
                "run_id": run_id,
                "worktree_path": str(worktree_path),
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_lock_data() -> None:
    """Remove the local runner lock file when present."""
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()


def run_command(
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    input_text: str | None = None,
) -> CommandResult:
    """Run a subprocess, capture logs, and return its outputs."""
    run_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "capture_output": True,
        "text": True,
        "input": input_text,
        "check": False,
    }
    if input_text is not None:
        # `codex exec -` requires UTF-8 on stdin; Windows locale encodings break non-ASCII prompts.
        run_kwargs["encoding"] = "utf-8"
        run_kwargs["errors"] = "replace"
    completed = subprocess.run(command, **run_kwargs)
    stdout_path.write_text(completed.stdout, encoding="utf-8", errors="ignore")
    stderr_path.write_text(completed.stderr, encoding="utf-8", errors="ignore")
    return CommandResult(
        command=" ".join(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def load_local_github_client() -> GitHubClient:
    """Build a GitHub client for local runner usage with repo autodetection."""
    token = get_env("GITHUB_TOKEN", required=True)
    repo = get_env("GITHUB_REPO", "")
    if not repo:
        repo = parse_repo_from_remote(run_git(["remote", "get-url", "origin"]))
    config = GitHubConfig(
        github_token=token,
        github_repo=repo,
        github_api_base=get_env("GITHUB_API_BASE", "https://api.github.com").rstrip("/"),
        github_api_version=get_env("GITHUB_API_VERSION", "2022-11-28"),
    )
    return GitHubClient(config)


def build_candidate(client: GitHubClient, pr: dict[str, Any]) -> QueueCandidate | None:
    """Check whether a PR is currently eligible for pickup."""
    pr_number = int(pr["number"])
    current_state = extract_primary_state(
        [
            str(label.get("name", "")).strip()
            for label in pr.get("labels", [])
            if isinstance(label, dict)
        ]
    )
    if current_state != "wf:codex-queued":
        return None

    head_repo = (((pr.get("head") or {}).get("repo")) or {}).get("full_name")
    same_repo = str(head_repo or "").strip() == client.config.github_repo
    if not same_repo:
        return None

    pr_files = client.list_pull_request_files(pr_number)
    request_path = next(
        (
            str(item.get("filename", "")).strip()
            for item in pr_files
            if str(item.get("filename", "")).startswith("docs/requests/")
            and str(item.get("filename", "")).endswith(".md")
        ),
        "",
    )
    if not request_path:
        return None

    comments = client.list_issue_comments(pr_number)
    latest_plan = find_latest_marker_comment(comments, MARKER_PLAN)
    latest_review = find_latest_marker_comment(comments, MARKER_GPT_REVIEW)
    latest_approve = find_latest_command_comment(comments, "/approve-plan")
    latest_fix = find_latest_command_comment(comments, "/codex-fix")

    if latest_plan is None or latest_approve is None:
        return None

    try:
        execution_mode = select_execution_mode(
            latest_plan_at=comment_timestamp(latest_plan).isoformat(),
            latest_approve_plan_at=comment_timestamp(
                latest_approve, prefer_updated=False
            ).isoformat(),
            latest_gpt_review_at=(
                latest_review and comment_timestamp(latest_review).isoformat()
            ),
            latest_codex_fix_at=(
                latest_fix and comment_timestamp(latest_fix, prefer_updated=False).isoformat()
            ),
        )
    except WorkflowError:
        return None

    queue_comment = latest_fix if execution_mode == "rework" and latest_fix else latest_approve
    return QueueCandidate(
        pr_number=pr_number,
        queue_time=comment_timestamp(queue_comment, prefer_updated=False).isoformat(),
        execution_mode=execution_mode,
        request_path=request_path,
        plan_comment=latest_plan,
        review_comment=latest_review,
        approve_plan_comment=latest_approve,
        codex_fix_comment=latest_fix,
        head_branch=str(((pr.get("head") or {}).get("ref")) or "").strip(),
        same_repo=same_repo,
    )


def select_next_candidate(
    client: GitHubClient, target_pr_number: int | None = None
) -> QueueCandidate | None:
    """Pick the next queued PR using FIFO by queue time."""
    prs = client.list_open_pull_requests()
    candidates: list[QueueCandidate] = []

    for pr in prs:
        if target_pr_number is not None and int(pr["number"]) != target_pr_number:
            continue
        candidate = build_candidate(client, pr)
        if candidate:
            candidates.append(candidate)

    if target_pr_number is not None and not candidates:
        raise WorkflowError(f"PR #{target_pr_number} is not eligible for runner pickup.")

    if not candidates:
        return None

    return min(candidates, key=lambda item: parse_timestamp(item.queue_time))


def mark_failed_run(
    client: GitHubClient,
    pr_number: int,
    run_id: str,
    failure_step: str,
    verification_summary: list[str],
    notes: str,
) -> None:
    """Publish a failed wf:codex-run comment and move the PR to wf:failed."""
    body = render_codex_run_comment(
        status="failed",
        run_id=run_id,
        verification_summary=verification_summary,
        run_result_path=None,
        commit_id=None,
        tag=None,
        failure_step=failure_step,
        notes=notes,
    )
    client.upsert_marker_comment(pr_number, MARKER_CODEX_RUN, body)
    client.set_primary_state(pr_number, "wf:failed")


def handle_stale_or_interrupted_jobs(client: GitHubClient) -> None:
    """Fail interrupted jobs left behind from a previous runner crash."""
    lock_data = read_lock_data()
    if lock_data is not None:
        pid = int(lock_data.get("pid", 0))
        if pid and pid_is_running(pid):
            raise WorkflowError(
                f"Another local runner job is active for PR #{lock_data.get('pr_number')}."
            )

        clear_lock_data()
        pr_number = int(lock_data.get("pr_number", 0) or 0)
        if pr_number:
            pr = client.get_pull_request(pr_number)
            current_state = extract_primary_state(
                [
                    str(label.get("name", "")).strip()
                    for label in pr.get("labels", [])
                    if isinstance(label, dict)
                ]
            )
            if current_state == "wf:codex-running":
                mark_failed_run(
                    client,
                    pr_number=pr_number,
                    run_id=str(lock_data.get("run_id", "interrupted-run")),
                    failure_step="interrupted",
                    verification_summary=["Runner process exited before completion."],
                    notes=(
                        "The previous local runner job was interrupted. "
                        "Worktree and logs are preserved on the Windows host."
                    ),
                )

    for pr in client.list_open_pull_requests():
        current_state = extract_primary_state(
            [
                str(label.get("name", "")).strip()
                for label in pr.get("labels", [])
                if isinstance(label, dict)
            ]
        )
        if current_state != "wf:codex-running":
            continue
        mark_failed_run(
            client,
            pr_number=int(pr["number"]),
            run_id=f"interrupted-pr-{pr['number']}",
            failure_step="interrupted",
            verification_summary=["Runner state was left in wf:codex-running without an active lock."],
            notes="The next runner cycle marked this interrupted phase-1 job as failed.",
        )


def create_worktree(candidate: QueueCandidate, timestamp_token: str) -> tuple[Path, str]:
    """Create an isolated worktree on a unique local branch."""
    worktree_name = f"pr-{candidate.pr_number}-{timestamp_token}".replace("/", "-")
    worktree_path = WORKTREE_ROOT / worktree_name
    local_branch = f"runner-pr-{candidate.pr_number}-{timestamp_token}".replace("/", "-")

    run_git(["fetch", "origin", candidate.head_branch])
    if worktree_path.exists():
        shutil.rmtree(worktree_path)
    run_git(
        [
            "worktree",
            "add",
            "-B",
            local_branch,
            str(worktree_path),
            f"origin/{candidate.head_branch}",
        ]
    )
    return worktree_path, local_branch


def cleanup_success_worktree(worktree_path: Path, local_branch: str) -> None:
    """Remove the temporary worktree after a successful push."""
    run_git(["worktree", "remove", "--force", str(worktree_path)])
    run_git(["branch", "-D", local_branch])


def build_execution_prompt(
    candidate: QueueCandidate,
    request_doc: str,
    plan_comment_body: str,
    review_comment_body: str | None,
) -> str:
    """Build the prompt passed to local `codex exec`."""
    common = (
        "You are the local desktop Codex runner for the phase-1 PR-driven RTL frontend flow.\n"
        "Implement the approved frontend work only. Do not replan. Do not commit, tag, push, "
        "or edit docs/runs output artifacts; the outer runner handles git and reporting.\n"
        "Keep edits inside the smallest safe scope required by the approved work.\n\n"
        f"## Request Document\n{request_doc}\n\n"
        f"## Latest wf:plan Comment\n{plan_comment_body}\n\n"
    )

    if candidate.execution_mode == "rework":
        return (
            common
            + "## Repair Mode\n"
            + "This run was requeued by /codex-fix from wf:rework-needed. "
            + "Use the latest wf:gpt-review comment as the only repair input. "
            + "Apply exactly one minimal repair round. Do not broaden scope.\n\n"
            + f"## Latest wf:gpt-review Comment\n{review_comment_body or '(missing review comment)'}\n"
        )

    return (
        common
        + "## Execution Mode\n"
        + "This is the initial approved plan execution round. Follow the latest wf:plan comment.\n"
    )


def run_codex_exec(
    worktree_path: Path,
    log_dir: Path,
    prompt: str,
) -> CommandResult:
    """Run local Codex against the isolated worktree."""
    output_last_message = log_dir / "codex_last_message.txt"
    return run_command(
        [
            "cmd",
            "/c",
            "codex",
            "exec",
            "--full-auto",
            "-C",
            str(worktree_path),
            "-o",
            str(output_last_message),
            "-",
        ],
        cwd=REPO_ROOT,
        stdout_path=log_dir / "codex_stdout.log",
        stderr_path=log_dir / "codex_stderr.log",
        input_text=prompt,
    )


def run_verification(worktree_path: Path, log_dir: Path) -> tuple[list[str], list[str]]:
    """Run the fixed phase-1 frontend verification commands."""
    summaries: list[str] = []
    commands: list[str] = []

    sim_result = run_command(
        ["cmd", "/c", "sim\\run_iverilog.bat"],
        cwd=worktree_path,
        stdout_path=log_dir / "sim_run_iverilog.log",
        stderr_path=log_dir / "sim_run_iverilog.err.log",
    )
    commands.append("cmd /c sim/run_iverilog.bat")
    if sim_result.returncode != 0:
        raise WorkflowError(
            "sim/run_iverilog.bat failed: "
            f"{sim_result.stderr.strip() or sim_result.stdout.strip()}"
        )
    if "Simulation Passed" not in sim_result.stdout:
        raise WorkflowError("sim/run_iverilog.bat output did not include 'Simulation Passed'.")
    summaries.append("sim/run_iverilog.bat: PASS")

    golden_result = run_command(
        [
            "python",
            "tools/check_golden.py",
            "--sim-log",
            str(log_dir / "sim_run_iverilog.log"),
        ],
        cwd=worktree_path,
        stdout_path=log_dir / "check_golden.log",
        stderr_path=log_dir / "check_golden.err.log",
    )
    commands.append("python tools/check_golden.py")
    if golden_result.returncode != 0:
        raise WorkflowError(
            "python tools/check_golden.py failed: "
            f"{golden_result.stderr.strip() or golden_result.stdout.strip()}"
        )
    summaries.append("python tools/check_golden.py: PASS")

    return commands, summaries


def write_run_result_file(
    worktree_path: Path,
    request_id: str,
    run_id: str,
    version: str,
    tag: str,
    commands_executed: list[str],
    verification_summary: list[str],
    log_dir: Path,
    timestamp_token: str,
) -> str:
    """Write the repository run result document for a successful run."""
    run_dir = worktree_path / "docs" / "runs" / request_id
    run_dir.mkdir(parents=True, exist_ok=True)
    relative_path = Path("docs") / "runs" / request_id / f"{timestamp_token}.md"
    full_path = worktree_path / relative_path
    full_path.write_text(
        render_run_result_document(
            request_id=request_id,
            run_id=run_id,
            version=version,
            tag=tag,
            commands_executed=commands_executed,
            verification_summary=verification_summary,
            artifact_paths=[relative_path.as_posix(), str(log_dir)],
            notes="Successful phase-1 frontend run.",
        ),
        encoding="utf-8",
    )
    return relative_path.as_posix()


def commit_and_tag_success(
    worktree_path: Path,
    run_id: str,
    execution_mode: str,
    tag: str,
) -> str:
    """Create the success commit and annotated tag inside the worktree."""
    run_git(["add", "-A"], cwd=worktree_path)
    prefix = "fix" if execution_mode == "rework" else "feat"
    run_git(
        ["commit", "-m", f"{prefix}: apply frontend run {run_id}"],
        cwd=worktree_path,
    )
    run_git(
        ["tag", "-a", tag, "-m", f"Phase-1 frontend pass {run_id}"],
        cwd=worktree_path,
    )
    return run_git(["rev-parse", "HEAD"], cwd=worktree_path)


def push_success_result(worktree_path: Path, head_branch: str, tag: str) -> None:
    """Push the updated PR branch and success tag back to origin."""
    run_git(["push", "origin", f"HEAD:{head_branch}"], cwd=worktree_path)
    run_git(["push", "origin", tag], cwd=worktree_path)


def execute_candidate(client: GitHubClient, candidate: QueueCandidate) -> None:
    """Run one eligible PR end-to-end through local Codex and fixed verification."""
    ensure_local_dirs()

    timestamp_token = format_timestamp_token()
    run_id = f"run-{timestamp_token}-pending"
    log_dir = LOG_ROOT / run_id
    log_dir.mkdir(parents=True, exist_ok=True)

    worktree_path: Path | None = None
    local_branch = ""
    verification_summary: list[str] = []
    failure_step = "execution"

    try:
        worktree_path, local_branch = create_worktree(candidate, timestamp_token)
        client.set_primary_state(candidate.pr_number, "wf:codex-running")

        request_doc = read_text_file(worktree_path / candidate.request_path)
        request_metadata = parse_request_metadata(request_doc)
        request_id = request_metadata["request_id"]
        version = request_metadata["version"]
        run_id = build_run_id(timestamp_token, version)
        tag = build_success_tag(timestamp_token, version)
        if log_dir.name != run_id:
            desired_log_dir = LOG_ROOT / run_id
            if log_dir.exists() and not desired_log_dir.exists():
                log_dir.rename(desired_log_dir)
            log_dir = desired_log_dir
            log_dir.mkdir(parents=True, exist_ok=True)
        write_lock_data(candidate.pr_number, run_id, worktree_path)

        plan_comment_body = str(candidate.plan_comment.get("body", "")).strip()
        review_comment_body = (
            str(candidate.review_comment.get("body", "")).strip()
            if candidate.review_comment is not None
            else None
        )
        prompt = build_execution_prompt(
            candidate,
            request_doc=request_doc,
            plan_comment_body=plan_comment_body,
            review_comment_body=review_comment_body,
        )

        codex_result = run_codex_exec(worktree_path, log_dir, prompt)
        if codex_result.returncode != 0:
            raise WorkflowError(
                "codex exec failed: "
                f"{codex_result.stderr.strip() or codex_result.stdout.strip()}"
            )

        failure_step = "verification"
        verification_commands, verification_summary = run_verification(worktree_path, log_dir)
        run_result_path = write_run_result_file(
            worktree_path=worktree_path,
            request_id=request_id,
            run_id=run_id,
            version=version,
            tag=tag,
            commands_executed=[
                "cmd /c codex exec --full-auto -C <worktree> -",
                *verification_commands,
            ],
            verification_summary=verification_summary,
            log_dir=log_dir,
            timestamp_token=timestamp_token,
        )

        failure_step = "git"
        commit_id = commit_and_tag_success(
            worktree_path=worktree_path,
            run_id=run_id,
            execution_mode=candidate.execution_mode,
            tag=tag,
        )

        failure_step = "push"
        client.set_primary_state(candidate.pr_number, "wf:awaiting-gpt-review")
        push_success_result(worktree_path, candidate.head_branch, tag)

        failure_step = "reporting"
        body = render_codex_run_comment(
            status="success",
            run_id=run_id,
            verification_summary=verification_summary,
            run_result_path=run_result_path,
            commit_id=commit_id,
            tag=tag,
            failure_step=None,
            notes="Ready for GPT frontend review.",
        )
        client.upsert_marker_comment(candidate.pr_number, MARKER_CODEX_RUN, body)
        cleanup_success_worktree(worktree_path, local_branch)
    except Exception as error:
        notes = (
            f"{error}\n"
            f"Local logs: {log_dir}\n"
            + (f"Preserved worktree: {worktree_path}" if worktree_path else "Worktree was not created.")
        )
        mark_failed_run(
            client,
            pr_number=candidate.pr_number,
            run_id=run_id,
            failure_step=failure_step,
            verification_summary=verification_summary or ["Local run failed before verification completed."],
            notes=notes,
        )
        raise
    finally:
        clear_lock_data()


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for local runner pickup."""
    parser = argparse.ArgumentParser(description="Pick up one queued phase-1 PR locally.")
    parser.add_argument("--pr-number", type=int, help="Process a specific PR number.")
    return parser.parse_args()


def main() -> int:
    """Entry point for the local runner automation."""
    args = parse_args()
    ensure_local_dirs()
    client = load_local_github_client()
    try:
        handle_stale_or_interrupted_jobs(client)
        candidate = select_next_candidate(client, target_pr_number=args.pr_number)
        if candidate is None:
            print("No eligible wf:codex-queued PR was found.")
            return 0

        execute_candidate(client, candidate)
        print(f"Completed local runner job for PR #{candidate.pr_number}.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
