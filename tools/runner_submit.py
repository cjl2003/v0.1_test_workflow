#!/usr/bin/env python3
"""Create a request document, open a PR, and set the initial phase-1 state."""

from __future__ import annotations

import argparse
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from tools.workflow_lib import GitHubClient, GitHubConfig, WorkflowError, get_env


REPO_ROOT = Path(__file__).resolve().parents[1]


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "request"


def run_git(args: list[str], cwd: Path = REPO_ROOT) -> str:
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


def current_branch() -> str:
    branch = run_git(["branch", "--show-current"])
    return branch or "main"


def render_request_document(
    request_id: str,
    title: str,
    stage: str,
    base_branch: str,
    work_branch: str,
    goal: str,
) -> str:
    return (
        f"# Frontend Request: {title}\n\n"
        f"- Request Id: `{request_id}`\n"
        f"- Title: `{title}`\n"
        f"- Stage: `{stage}`\n"
        f"- Base Branch: `{base_branch}`\n"
        f"- Work Branch: `{work_branch}`\n"
        f"- Version: `r001`\n\n"
        "## Goal\n"
        f"{goal.strip()}\n\n"
        "## In-Scope Items\n"
        f"- {goal.strip()}\n"
        "- Only the current phase-1 frontend workflow defined in the repository spec.\n\n"
        "## Out-of-Scope Items\n"
        "- Remote server execution.\n"
        "- Backend optimization, synthesis, STA, power, area, formal, LVS, or PnR.\n"
        "- Automatic replan or rerun behavior.\n\n"
        "## Acceptance Criteria\n"
        "- GitHub publishes either wf:clarification or wf:plan.\n"
        "- Local execution, when approved, passes sim/run_iverilog.bat.\n"
        "- Local execution, when approved, passes python tools/check_golden.py.\n"
        "- Final GPT frontend review reaches wf:frontend-passed or wf:rework-needed.\n\n"
        "## Operating Constraints\n"
        "- Follow docs/superpowers/specs/2026-04-17-pr-driven-rtl-frontend-autoflow-design.md exactly.\n"
        "- Do not extend beyond phase-1.\n"
        "- Do not auto-replan or auto-rerun.\n"
    ).strip() + "\n"


def parse_repo_from_remote(remote_url: str) -> str:
    remote = remote_url.strip()
    ssh_match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", remote)
    if ssh_match:
        return ssh_match.group(1)

    https_match = re.match(r"https://github\.com/(.+?)(?:\.git)?$", remote)
    if https_match:
        return https_match.group(1)

    raise WorkflowError(f"Unsupported origin URL for GitHub repo detection: {remote}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit a phase-1 frontend request.")
    parser.add_argument("goal", help="Natural-language frontend request.")
    parser.add_argument("--title", help="Explicit PR/request title.")
    parser.add_argument("--base-branch", help="Base branch for the PR.")
    parser.add_argument("--work-branch", help="Work branch to create for the request.")
    parser.add_argument("--stage", default="phase-1", help="Request stage label.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y%m%d-%H%M%S")

    title = args.title or args.goal.strip().splitlines()[0][:80]
    base_branch = args.base_branch or current_branch()
    work_branch = args.work_branch or f"request/{date_part}-{slugify(title)}"
    request_id = f"req-{stamp}-{slugify(title)}"

    run_git(["checkout", base_branch])
    run_git(["checkout", "-b", work_branch])

    request_dir = REPO_ROOT / "docs" / "requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    request_path = request_dir / f"{date_part}-{slugify(title)}.md"
    request_path.write_text(
        render_request_document(
            request_id=request_id,
            title=title,
            stage=args.stage,
            base_branch=base_branch,
            work_branch=work_branch,
            goal=args.goal,
        ),
        encoding="utf-8",
    )

    run_git(["add", str(request_path)])
    run_git(["commit", "-m", f"feat: create frontend request {request_id}"])
    run_git(["push", "-u", "origin", work_branch])

    github_repo = get_env("GITHUB_REPO", "")
    if not github_repo:
        github_repo = parse_repo_from_remote(run_git(["remote", "get-url", "origin"]))

    github_config = GitHubConfig(
        github_token=get_env("GITHUB_TOKEN", required=True),
        github_repo=github_repo,
        github_api_base=get_env("GITHUB_API_BASE", "https://api.github.com").rstrip("/"),
        github_api_version=get_env("GITHUB_API_VERSION", "2022-11-28"),
    )

    client = GitHubClient(github_config)
    try:
        pr = client.create_pull_request(
            title=title,
            body=(
                f"Phase-1 frontend request created from desktop Codex.\n\n"
                f"- Request Id: `{request_id}`\n"
                f"- Request File: `{request_path.as_posix()}`\n"
            ),
            head_branch=work_branch,
            base_branch=base_branch,
        )
        pr_number = int(pr["number"])
        client.ensure_primary_labels_exist()
        client.set_primary_state(pr_number, "wf:intake")
        print(str(pr.get("html_url", "")))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
