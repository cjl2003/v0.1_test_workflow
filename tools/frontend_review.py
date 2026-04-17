#!/usr/bin/env python3
"""Run the GitHub-side GPT frontend re-review for a completed local run."""

from __future__ import annotations

import argparse
import re
import textwrap
from typing import Any

from tools.workflow_lib import (
    GitHubClient,
    MARKER_CODEX_RUN,
    MARKER_GPT_REVIEW,
    MARKER_PLAN,
    RenderedComment,
    WorkflowError,
    call_openai_json,
    extract_comment_field,
    extract_primary_state,
    find_latest_marker_comment,
    get_env,
    indent_block,
    load_github_config,
    load_openai_config,
    render_marked_comment,
    truncate_text,
)

WORKFLOW_ARTIFACT_PREFIXES = ("docs/requests/", "docs/runs/")


def partition_changed_paths(diff_text: str) -> tuple[list[str], list[str]]:
    """Split changed paths into scoped content files and allowed workflow artifacts."""
    all_paths: list[str] = []
    for line in diff_text.splitlines():
        match = re.match(r"^diff --git a/(.+?) b/(.+)$", line.strip())
        if not match:
            continue
        path = match.group(2).strip()
        if path not in all_paths:
            all_paths.append(path)

    scoped_paths: list[str] = []
    artifact_paths: list[str] = []
    for path in all_paths:
        if path.startswith(WORKFLOW_ARTIFACT_PREFIXES):
            artifact_paths.append(path)
        else:
            scoped_paths.append(path)
    return scoped_paths, artifact_paths


def normalize_review_payload(payload: dict[str, Any]) -> RenderedComment:
    """Turn model JSON into the canonical machine-readable GPT review comment."""
    outcome = str(payload.get("outcome", "")).strip().lower()
    summary = str(payload.get("summary", "")).strip()
    findings = [str(item).strip() for item in payload.get("findings", []) if str(item).strip()]
    next_checks = [
        str(item).strip() for item in payload.get("next_checks", []) if str(item).strip()
    ]

    if outcome not in {"pass", "rework-needed"}:
        raise WorkflowError(f"Unsupported review outcome: {outcome!r}")
    if not summary:
        raise WorkflowError("Review payload must include a non-empty summary.")

    body = render_marked_comment(
        MARKER_GPT_REVIEW,
        "Frontend Review",
        [("Outcome", outcome)],
        [
            ("Summary", summary),
            ("Findings", findings or ["No blocking findings."]),
            ("Next Checks", next_checks or ["No additional checks."]),
        ],
    )

    target_state = "wf:frontend-passed" if outcome == "pass" else "wf:rework-needed"
    return RenderedComment(MARKER_GPT_REVIEW, target_state, body)


def build_review_instructions() -> str:
    """High-priority instructions for the frontend review model."""
    return textwrap.dedent(
        """
        You are the GitHub-side GPT-5.4 frontend reviewer in a phase-1 PR-driven RTL workflow.
        Review only whether the latest local Codex run satisfies the approved plan and verification.

        Rules:
        - You must return exactly one outcome: "pass" or "rework-needed".
        - Stay inside phase-1. Do not propose replanning, rerunning, or backend expansion.
        - If rework is needed, scope it to the latest changed code and run result evidence.
        - Treat `docs/requests/*.md` and `docs/runs/**` as allowed phase-1 workflow artifacts; do not treat them as scope violations.
        - Keep the review grounded in the provided diff, plan, codex-run comment, and run result.
        - Return JSON only.

        JSON shape:
        {
          "outcome": "pass" | "rework-needed",
          "summary": "short paragraph",
          "findings": ["finding 1", "finding 2"],
          "next_checks": ["check 1", "check 2"]
        }
        """
    ).strip()


def load_review_context(pr_number: int, client: GitHubClient) -> str:
    """Build the reviewer prompt from the latest diff and workflow artifacts."""
    comments = client.list_issue_comments(pr_number)
    latest_plan = find_latest_marker_comment(comments, MARKER_PLAN)
    latest_run = find_latest_marker_comment(comments, MARKER_CODEX_RUN)

    if latest_plan is None:
        raise WorkflowError("Cannot run frontend review without a latest wf:plan comment.")
    if latest_run is None:
        raise WorkflowError("Cannot run frontend review without a latest wf:codex-run comment.")

    diff_text = client.fetch_pull_request_diff(pr_number)
    scoped_paths, artifact_paths = partition_changed_paths(diff_text)
    plan_body = str(latest_plan.get("body", "")).strip()
    run_body = str(latest_run.get("body", "")).strip()

    run_result_path = (
        extract_comment_field(run_body, "Run Result Path")
        or extract_comment_field(run_body, "Run Result")
    )
    if not run_result_path:
        raise WorkflowError("wf:codex-run comment is missing Run Result Path.")

    run_result = client.fetch_pull_request_file_text(pr_number, run_result_path)

    blocks = [
        indent_block("Latest Approved Plan", plan_body),
        indent_block("Latest Codex Run Comment", run_body),
        indent_block("Latest Run Result Document", truncate_text(run_result, 12000)),
        indent_block(
            "Changed File Classification",
            "\n".join(
                [
                    "Scoped content changes:",
                    *([f"- {path}" for path in scoped_paths] or ["- (none)"]),
                    "",
                    "Allowed phase-1 workflow artifacts:",
                    *([f"- {path}" for path in artifact_paths] or ["- (none)"]),
                ]
            ),
        ),
        indent_block("Latest Pull Request Diff", truncate_text(diff_text, 24000)),
    ]
    return "\n\n".join(blocks)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments used by GitHub Actions."""
    parser = argparse.ArgumentParser(description="Run the phase-1 frontend re-review.")
    parser.add_argument("pr_number", type=int, nargs="?", help="Pull request number.")
    return parser.parse_args()


def main() -> int:
    """Entry point for `frontend-review.yml`."""
    args = parse_args()
    pr_number = args.pr_number or int(get_env("PR_NUMBER", required=True))

    github_config = load_github_config()
    openai_config = load_openai_config()
    client = GitHubClient(github_config)
    try:
        pr = client.get_pull_request(pr_number)
        current_state = extract_primary_state(
            [
                str(label.get("name", "")).strip()
                for label in pr.get("labels", [])
                if isinstance(label, dict)
            ]
        )
        if current_state != "wf:awaiting-gpt-review":
            print("Skipping frontend review because the PR is not in wf:awaiting-gpt-review.")
            return 0

        prompt = load_review_context(pr_number, client)
        payload, response_id = call_openai_json(
            openai_config, build_review_instructions(), prompt
        )
        rendered = normalize_review_payload(payload)

        body = f"{rendered.body}\n\n- OpenAI Response Id: `{response_id}`"
        client.ensure_primary_labels_exist()
        client.upsert_marker_comment(pr_number, rendered.marker, body)
        client.set_primary_state(pr_number, rendered.target_state)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
