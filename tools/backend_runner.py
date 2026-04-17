#!/usr/bin/env python3
"""Helpers for the local phase-2A backend pickup flow."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.backend_baseline import (
    build_phase2a_local_dir,
    build_phase2a_repo_dir,
    build_phase2a_run_id,
    build_phase2a_tag,
    render_phase2a_run_comment,
)
from tools.workflow_lib import (
    MARKER_BACKEND_RUN,
    WorkflowError,
    comment_timestamp,
    extract_primary_state,
    find_latest_command_comment,
    read_text_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SSH_INFO_PATH = Path.home() / ".codex" / "secrets" / "huada_ssh.txt"
LOCAL_STATE_ROOT = Path.home() / ".codex-phase2a-runner"
WORKTREE_ROOT = LOCAL_STATE_ROOT / "worktrees"
LOG_ROOT = LOCAL_STATE_ROOT / "logs"

REQUEST_FIELDS = {
    "Request Id": "request_id",
    "Version": "version",
}

_REQUIRED_LOCAL_OUTPUTS = (
    "summary.md",
    "manifest.json",
    "mapped.v",
    "logs/synthesis.log",
    "logs/formal_ec.log",
)

_REQUIRED_REPO_OUTPUTS = (
    "summary.md",
    "manifest.json",
    "reports/synthesis_power.rpt",
    "reports/synthesis_area.rpt",
    "reports/synthesis_timing_summary.rpt",
    "reports/constraint_summary.md",
    "reports/formal_ec_summary.md",
)


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class BackendCandidate:
    pr_number: int
    queue_time: str
    request_path: str
    head_branch: str
    same_repo: bool = True
    queue_kind: str = "backend"


def format_timestamp_token(moment: datetime | None = None) -> str:
    """Build the shared phase-2A timestamp token."""
    moment = moment or datetime.now(timezone.utc)
    return moment.strftime("%Y%m%d_%H%M%S")


def parse_request_metadata(request_doc: str) -> dict[str, str]:
    """Extract the request id and version from the request document."""
    metadata: dict[str, str] = {}
    for label, key in REQUEST_FIELDS.items():
        pattern = re.compile(rf"^- {re.escape(label)}:\s+`(.+?)`\s*$", re.MULTILINE)
        match = pattern.search(request_doc)
        if not match:
            raise WorkflowError(f"Request document is missing required field: {label}")
        metadata[key] = match.group(1).strip()
    return metadata


def ensure_local_dirs() -> None:
    """Create local directories used by the phase-2A runner."""
    for path in (LOCAL_STATE_ROOT, WORKTREE_ROOT, LOG_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def build_phase2a_prompt(request_doc: str, run_id: str) -> str:
    """Build the minimal phase-2A backend execution prompt."""
    return (
        "You are the local desktop Codex backend runner for phase-2A.\n"
        "Execute only logic synthesis, mapped netlist generation, Formal EC, and baseline report collection.\n"
        "Use C:\\Users\\lalala\\.codex\\secrets\\huada_ssh.txt for SSH details.\n"
        "Use the Huada remote skill chain to locate the correct synthesis and Formal EC tools.\n"
        "Save the Windows master package under C:\\Users\\lalala\\.codex\\backend_runs\\ using the request id and run id.\n"
        "Write the slim repository artifact set under docs/runs/<request_id>/backend/<run_id>/.\n"
        "Do not run place and route, signoff STA, LVS, SPEF, or any optimization loop.\n\n"
        f"## Run Id\n{run_id}\n\n"
        f"## Request Document\n{request_doc.strip()}\n"
    )


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


def create_backend_worktree(candidate: BackendCandidate, timestamp_token: str) -> tuple[Path, str]:
    """Create an isolated worktree on a unique local branch for phase-2A."""
    worktree_name = f"backend-pr-{candidate.pr_number}-{timestamp_token}".replace("/", "-")
    worktree_path = WORKTREE_ROOT / worktree_name
    local_branch = f"backend-runner-pr-{candidate.pr_number}-{timestamp_token}".replace("/", "-")

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


def validate_phase2a_outputs(local_dir: Path, repo_dir: Path) -> list[str]:
    """Return any required phase-2A artifacts that are still missing."""
    missing: list[str] = []

    for relative_path in _REQUIRED_LOCAL_OUTPUTS:
        if not (local_dir / relative_path).exists():
            missing.append(relative_path)

    for relative_path in _REQUIRED_REPO_OUTPUTS:
        if not (repo_dir / relative_path).exists():
            missing.append(relative_path)

    return missing


def run_codex_exec(worktree_path: Path, log_dir: Path, prompt: str) -> CommandResult:
    """Run local Codex against the isolated phase-2A worktree."""
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


def build_backend_candidate(client: Any, pr: dict[str, Any]) -> BackendCandidate | None:
    """Build a phase-2A backend candidate from a PR when eligible."""
    pr_number = int(pr["number"])
    current_state = extract_primary_state(
        [
            str(label.get("name", "")).strip()
            for label in pr.get("labels", [])
            if isinstance(label, dict)
        ]
    )
    if current_state != "wf:backend-queued":
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
    latest_continue = find_latest_command_comment(comments, "/continue-backend")
    if latest_continue is None:
        return None

    return BackendCandidate(
        pr_number=pr_number,
        queue_time=comment_timestamp(latest_continue, prefer_updated=False).isoformat(),
        request_path=request_path,
        head_branch=str(((pr.get("head") or {}).get("ref")) or "").strip(),
        same_repo=same_repo,
    )


def _summarize_report(path: Path) -> str:
    if not path.exists():
        return "missing"

    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        summary = line.strip()
        if summary:
            return summary[:160]
    return "captured"


def load_phase2a_baseline_metrics(repo_dir: Path) -> dict[str, str]:
    """Extract short headline metrics from the required synthesis reports."""
    reports_dir = repo_dir / "reports"
    return {
        "power": _summarize_report(reports_dir / "synthesis_power.rpt"),
        "area": _summarize_report(reports_dir / "synthesis_area.rpt"),
        "timing": _summarize_report(reports_dir / "synthesis_timing_summary.rpt"),
    }


def commit_and_tag_success(worktree_path: Path, run_id: str, tag: str) -> str:
    """Create the backend success commit and annotated tag."""
    run_git(["add", "-A"], cwd=worktree_path)
    run_git(
        ["commit", "-m", f"feat: publish phase2a backend run {run_id}"],
        cwd=worktree_path,
    )
    run_git(
        ["tag", "-a", tag, "-m", f"Phase-2A backend pass {run_id}"],
        cwd=worktree_path,
    )
    return run_git(["rev-parse", "HEAD"], cwd=worktree_path)


def push_success_result(worktree_path: Path, head_branch: str, tag: str) -> None:
    """Push the updated PR branch and backend tag back to origin."""
    run_git(["push", "origin", f"HEAD:{head_branch}"], cwd=worktree_path)
    run_git(["push", "origin", tag], cwd=worktree_path)


def mark_backend_failed_run(
    client: Any,
    pr_number: int,
    run_id: str,
    local_package_dir: str,
    repo_artifact_dir: str,
    notes: str,
) -> None:
    """Publish a failed wf:backend-run comment and move the PR to wf:backend-failed."""
    body = render_phase2a_run_comment(
        status="failed",
        run_id=run_id,
        commit_id=None,
        tag=None,
        local_package_dir=local_package_dir,
        repo_artifact_dir=repo_artifact_dir,
        synthesis_status="failed",
        mapped_netlist_status="unknown",
        constraints_status="unknown",
        formal_ec_status="unknown",
        baseline_metrics={},
        notes=notes,
    )
    client.upsert_marker_comment(pr_number, MARKER_BACKEND_RUN, body)
    client.set_primary_state(pr_number, "wf:backend-failed")


def execute_backend_candidate(client: Any, candidate: BackendCandidate) -> None:
    """Run one queued phase-2A backend candidate through the local backend flow."""
    ensure_local_dirs()

    timestamp_token = format_timestamp_token()
    run_id = build_phase2a_run_id(timestamp_token, "pending")

    if not SSH_INFO_PATH.exists():
        local_dir = build_phase2a_local_dir("pending-request", run_id)
        repo_dir = build_phase2a_repo_dir("pending-request", run_id)
        body = render_phase2a_run_comment(
            status="blocked",
            run_id=run_id,
            commit_id=None,
            tag=None,
            local_package_dir=str(local_dir),
            repo_artifact_dir=repo_dir.as_posix(),
            synthesis_status="not-started",
            mapped_netlist_status="missing",
            constraints_status="unknown",
            formal_ec_status="not-started",
            baseline_metrics={},
            notes="Waiting for refreshed SSH info.",
        )
        client.upsert_marker_comment(candidate.pr_number, MARKER_BACKEND_RUN, body)
        client.set_primary_state(candidate.pr_number, "wf:backend-blocked")
        return

    log_dir = LOG_ROOT / run_id
    log_dir.mkdir(parents=True, exist_ok=True)

    worktree_path: Path | None = None
    local_branch = ""
    local_dir = build_phase2a_local_dir("pending-request", run_id)
    repo_dir_relative = build_phase2a_repo_dir("pending-request", run_id)
    repo_dir = REPO_ROOT / repo_dir_relative

    try:
        worktree_path, local_branch = create_backend_worktree(candidate, timestamp_token)
        client.set_primary_state(candidate.pr_number, "wf:backend-running")

        request_doc = read_text_file(worktree_path / candidate.request_path)
        metadata = parse_request_metadata(request_doc)
        request_id = metadata["request_id"]
        version = metadata["version"]
        run_id = build_phase2a_run_id(timestamp_token, version)
        tag = build_phase2a_tag("pass", timestamp_token, version)

        if log_dir.name != run_id:
            desired_log_dir = LOG_ROOT / run_id
            if log_dir.exists() and not desired_log_dir.exists():
                log_dir.rename(desired_log_dir)
            log_dir = desired_log_dir
            log_dir.mkdir(parents=True, exist_ok=True)

        local_dir = build_phase2a_local_dir(request_id, run_id)
        local_dir.mkdir(parents=True, exist_ok=True)
        repo_dir_relative = build_phase2a_repo_dir(request_id, run_id)
        repo_dir = worktree_path / repo_dir_relative
        repo_dir.mkdir(parents=True, exist_ok=True)

        prompt = build_phase2a_prompt(request_doc, run_id)
        codex_result = run_codex_exec(worktree_path, log_dir, prompt)
        if codex_result.returncode != 0:
            raise WorkflowError(
                "codex exec failed: "
                f"{codex_result.stderr.strip() or codex_result.stdout.strip()}"
            )

        missing = validate_phase2a_outputs(local_dir, repo_dir)
        if missing:
            raise WorkflowError(
                "Phase-2A outputs missing required files: " + ", ".join(sorted(missing))
            )

        baseline_metrics = load_phase2a_baseline_metrics(repo_dir)
        commit_id = commit_and_tag_success(worktree_path, run_id, tag)
        client.set_primary_state(candidate.pr_number, "wf:awaiting-backend-review")
        push_success_result(worktree_path, candidate.head_branch, tag)

        body = render_phase2a_run_comment(
            status="success",
            run_id=run_id,
            commit_id=commit_id,
            tag=tag,
            local_package_dir=str(local_dir),
            repo_artifact_dir=repo_dir_relative.as_posix(),
            synthesis_status="pass",
            mapped_netlist_status="present",
            constraints_status="loaded",
            formal_ec_status="pass",
            baseline_metrics=baseline_metrics,
            notes="Ready for backend review.",
        )
        client.upsert_marker_comment(candidate.pr_number, MARKER_BACKEND_RUN, body)
        cleanup_success_worktree(worktree_path, local_branch)
    except Exception as error:
        notes = (
            f"{error}\n"
            f"Local logs: {log_dir}\n"
            + (f"Preserved worktree: {worktree_path}" if worktree_path else "Worktree was not created.")
        )
        mark_backend_failed_run(
            client,
            pr_number=candidate.pr_number,
            run_id=run_id,
            local_package_dir=str(local_dir),
            repo_artifact_dir=repo_dir_relative.as_posix(),
            notes=notes,
        )
        raise
