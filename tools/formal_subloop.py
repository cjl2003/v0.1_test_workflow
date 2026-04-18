#!/usr/bin/env python3
"""Local desktop relay helper for the phase-2A lightweight Formal subloop."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.formal_protocol import render_formal_approval_comment
from tools.workflow_lib import (
    GitHubClient,
    MARKER_FORMAL_APPROVAL,
    MARKER_FORMAL_DIAGNOSE,
    MARKER_FORMAL_REVIEW_PLAN,
    WorkflowError,
    extract_comment_field,
    find_latest_marker_comment,
    load_github_config,
)


def post_formal_diagnose(client: GitHubClient, pr_number: int, body: str) -> None:
    if MARKER_FORMAL_DIAGNOSE not in body:
        raise WorkflowError("Formal diagnose body must include the wf:formal-diagnose marker.")
    client.create_marker_comment(pr_number, MARKER_FORMAL_DIAGNOSE, body)


def extract_latest_formal_review_plan_comment(
    client: GitHubClient, pr_number: int
) -> dict[str, object]:
    comments = client.list_issue_comments(pr_number)
    latest = find_latest_marker_comment(comments, MARKER_FORMAL_REVIEW_PLAN)
    if latest is None:
        raise WorkflowError("A latest wf:formal-review-plan comment is required.")
    return latest


def extract_latest_formal_review_plan(client: GitHubClient, pr_number: int) -> str:
    latest = extract_latest_formal_review_plan_comment(client, pr_number)
    return str(latest.get("body", "")).strip()


def approve_latest_formal_plan(client: GitHubClient, pr_number: int) -> None:
    latest_review_plan = extract_latest_formal_review_plan_comment(client, pr_number)
    review_body = str(latest_review_plan.get("body", "")).strip()
    plan_title = extract_comment_field(review_body, "Plan Title")
    if plan_title is None:
        raise WorkflowError("Latest wf:formal-review-plan is missing a Plan Title line.")
    review_plan_comment_id = latest_review_plan.get("id")
    if review_plan_comment_id in (None, ""):
        raise WorkflowError("Latest wf:formal-review-plan comment is missing an id.")
    review_plan_comment_url = str(latest_review_plan.get("html_url", "")).strip()
    if not review_plan_comment_url:
        raise WorkflowError("Latest wf:formal-review-plan comment is missing an html_url.")
    client.create_marker_comment(
        pr_number,
        MARKER_FORMAL_APPROVAL,
        render_formal_approval_comment(
            plan_title,
            str(review_plan_comment_id),
            review_plan_comment_url,
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Relay phase-2A lightweight Formal subloop comments."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose = subparsers.add_parser("post-diagnose", help="Post or update a Formal diagnose comment.")
    diagnose.add_argument("--pr-number", type=int, required=True)
    diagnose.add_argument("--body-file", type=Path, required=True)

    show_plan = subparsers.add_parser(
        "show-latest-plan", help="Print the latest Formal review-plan comment body."
    )
    show_plan.add_argument("--pr-number", type=int, required=True)

    approve = subparsers.add_parser("approve", help="Post a Formal approval comment.")
    approve.add_argument("--pr-number", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = GitHubClient(load_github_config())
    try:
        if args.command == "post-diagnose":
            body = args.body_file.read_text(encoding="utf-8")
            post_formal_diagnose(client, args.pr_number, body)
            return 0
        if args.command == "show-latest-plan":
            print(extract_latest_formal_review_plan(client, args.pr_number))
            return 0
        if args.command == "approve":
            approve_latest_formal_plan(client, args.pr_number)
            return 0
        raise WorkflowError(f"Unsupported command: {args.command}")
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
