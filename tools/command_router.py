#!/usr/bin/env python3
"""Route phase-1 PR slash commands into workflow-state transitions."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from tools.workflow_lib import (
    GitHubClient,
    MARKER_GPT_REVIEW,
    MARKER_PLAN,
    WorkflowError,
    comment_timestamp,
    extract_primary_state,
    find_latest_marker_comment,
    get_env,
    is_trusted_author,
    load_github_config,
    parse_timestamp,
)


@dataclass(frozen=True)
class CommandDecision:
    accepted: bool
    target_state: str | None
    reason: str


def evaluate_command(
    command: str,
    current_state: str | None,
    author_association: str,
    command_created_at: str,
    latest_plan_updated_at: str | None,
    latest_gpt_review_updated_at: str | None,
) -> CommandDecision:
    """Validate `/approve-plan` and `/codex-fix` against the phase-1 protocol."""
    normalized = command.strip()
    if not is_trusted_author(author_association):
        return CommandDecision(False, None, "Command author is not trusted.")

    command_time = parse_timestamp(command_created_at)

    if normalized.startswith("/approve-plan"):
        if current_state != "wf:awaiting-plan-approval":
            return CommandDecision(
                False,
                None,
                "Current primary state must be wf:awaiting-plan-approval.",
            )
        if not latest_plan_updated_at:
            return CommandDecision(False, None, "A latest wf:plan comment is required.")
        if command_time <= parse_timestamp(latest_plan_updated_at):
            return CommandDecision(
                False,
                None,
                "/approve-plan must be newer than the latest wf:plan comment.",
            )
        return CommandDecision(True, "wf:codex-queued", "Plan approval accepted.")

    if normalized.startswith("/codex-fix"):
        if current_state != "wf:rework-needed":
            return CommandDecision(
                False,
                None,
                "Current primary state must be wf:rework-needed.",
            )
        if not latest_gpt_review_updated_at:
            return CommandDecision(False, None, "A latest wf:gpt-review comment is required.")
        if command_time <= parse_timestamp(latest_gpt_review_updated_at):
            return CommandDecision(
                False,
                None,
                "/codex-fix must be newer than the latest wf:gpt-review comment.",
            )
        return CommandDecision(True, "wf:codex-queued", "Minimal repair round accepted.")

    return CommandDecision(False, None, f"Unsupported command: {normalized}")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments used by GitHub Actions."""
    parser = argparse.ArgumentParser(description="Route /approve-plan and /codex-fix.")
    parser.add_argument("pr_number", type=int, nargs="?", help="Pull request number.")
    parser.add_argument("--command-body", dest="command_body", help="Raw PR comment body.")
    parser.add_argument(
        "--command-created-at",
        dest="command_created_at",
        help="Timestamp for the PR comment event.",
    )
    parser.add_argument(
        "--author-association",
        dest="author_association",
        help="GitHub author association for the comment author.",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point for `command-router.yml`."""
    args = parse_args()
    github_config = load_github_config()

    pr_number = args.pr_number or int(get_env("PR_NUMBER", required=True))
    command_body = args.command_body or get_env("COMMAND_BODY", required=True)
    command_created_at = args.command_created_at or get_env(
        "COMMENT_CREATED_AT", required=True
    )
    author_association = args.author_association or get_env(
        "COMMENT_AUTHOR_ASSOCIATION", required=True
    )

    client = GitHubClient(github_config)
    try:
        pr = client.get_pull_request(pr_number)
        comments = client.list_issue_comments(pr_number)

        current_state = extract_primary_state(
            [
                str(label.get("name", "")).strip()
                for label in pr.get("labels", [])
                if isinstance(label, dict)
            ]
        )

        latest_plan = find_latest_marker_comment(comments, MARKER_PLAN)
        latest_review = find_latest_marker_comment(comments, MARKER_GPT_REVIEW)

        decision = evaluate_command(
            command=command_body,
            current_state=current_state,
            author_association=author_association,
            command_created_at=command_created_at,
            latest_plan_updated_at=(
                latest_plan and comment_timestamp(latest_plan).isoformat()
            ),
            latest_gpt_review_updated_at=(
                latest_review and comment_timestamp(latest_review).isoformat()
            ),
        )

        print(decision.reason)
        if not decision.accepted or not decision.target_state:
            return 0

        client.ensure_primary_labels_exist()
        client.set_primary_state(pr_number, decision.target_state)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
