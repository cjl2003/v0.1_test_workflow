#!/usr/bin/env python3
"""Run the GitHub-side GPT review-plan step for phase-2A Formal fail/undet rounds."""

from __future__ import annotations

import argparse
import textwrap
from typing import Any

from tools.formal_protocol import render_formal_review_plan_comment
from tools.workflow_lib import (
    GitHubClient,
    MARKER_BACKEND_RUN,
    MARKER_FORMAL_DIAGNOSE,
    MARKER_FORMAL_REVIEW_PLAN,
    RenderedComment,
    WorkflowError,
    call_openai_json,
    comment_timestamp,
    extract_comment_field,
    extract_primary_state,
    find_latest_marker_comment,
    get_env,
    indent_block,
    load_github_config,
    load_openai_config,
    truncate_text,
)


def _normalize_string_list(payload: dict[str, Any], field_name: str) -> list[str]:
    """Validate and normalize optional string-list fields from model JSON."""
    raw_items = payload.get(field_name, [])
    if raw_items is None:
        raise WorkflowError(f"Formal review-plan payload field {field_name} must be a list.")
    if not isinstance(raw_items, list):
        raise WorkflowError(f"Formal review-plan payload field {field_name} must be a list.")

    cleaned: list[str] = []
    for item in raw_items:
        if item is None:
            continue
        value = str(item).strip()
        if value:
            cleaned.append(value)
    return cleaned


def normalize_formal_review_plan_payload(payload: dict[str, Any]) -> RenderedComment:
    """Normalize model JSON into the canonical Formal review-plan comment."""
    decision = str(payload.get("decision", "")).strip().lower()
    reasons = _normalize_string_list(payload, "reasons")
    next_plan = payload.get("next_plan", {})
    success_criteria = str(payload.get("success_criteria", "")).strip()
    do_not_do = _normalize_string_list(payload, "do_not_do")

    if decision not in {"approve", "reject", "revise"}:
        raise WorkflowError(f"Unsupported formal review-plan decision: {decision!r}")
    if not isinstance(next_plan, dict):
        raise WorkflowError("Formal review-plan payload must include a next_plan object.")

    plan_title = str(next_plan.get("title", "")).strip()
    hypothesis = str(next_plan.get("hypothesis", "")).strip()
    one_experiment = str(next_plan.get("one_experiment", "")).strip()
    expected_evidence = str(next_plan.get("expected_evidence", "")).strip()
    stop_condition = str(next_plan.get("stop_condition", "")).strip()

    if not plan_title:
        raise WorkflowError("Formal review-plan payload must include next_plan.title.")
    if not hypothesis:
        raise WorkflowError("Formal review-plan payload must include next_plan.hypothesis.")
    if not one_experiment:
        raise WorkflowError("Formal review-plan payload must include next_plan.one_experiment.")
    if not expected_evidence:
        raise WorkflowError("Formal review-plan payload must include next_plan.expected_evidence.")
    if not stop_condition:
        raise WorkflowError("Formal review-plan payload must include next_plan.stop_condition.")
    if not success_criteria:
        raise WorkflowError("Formal review-plan payload must include success_criteria.")

    body = render_formal_review_plan_comment(
        decision=decision,
        reasons=reasons,
        plan_title=plan_title,
        hypothesis=hypothesis,
        one_experiment=one_experiment,
        expected_evidence=expected_evidence,
        stop_condition=stop_condition,
        success_criteria=success_criteria,
        do_not_do=do_not_do,
    )
    return RenderedComment(MARKER_FORMAL_REVIEW_PLAN, "wf:backend-failed", body)


def build_formal_review_plan_instructions() -> str:
    """High-priority instructions for the Formal review-plan model."""
    return textwrap.dedent(
        """
        You are the GitHub-side GPT-5.4 reviewer for the phase-2A lightweight Formal subloop.
        Review only the latest wf:formal-diagnose comment.

        Rules:
        - Return JSON only.
        - Allowed decisions: "approve", "reject", "revise".
        - You must provide exactly one next_plan object.
        - Do not provide parallel A/B plans.
        - Do not propose workflow refactors, broad backend redesign, or optimization loops.
        - Stay inside the current Formal fail/undet blocker.

        JSON shape:
        {
          "decision": "approve" | "reject" | "revise",
          "reasons": ["point 1", "point 2"],
          "next_plan": {
            "title": "short title",
            "hypothesis": "single hypothesis",
            "one_experiment": "one experiment or one fix direction",
            "expected_evidence": "what evidence should appear",
            "stop_condition": "where this round must stop"
          },
          "success_criteria": "one paragraph",
          "do_not_do": ["item 1", "item 2"]
        }
        """
    ).strip()


def load_formal_review_plan_context(pr_number: int, client: GitHubClient) -> str:
    """Build the prompt from the latest backend-run and formal-diagnose comments."""
    comments = client.list_issue_comments(pr_number)
    latest_formal_diagnose = find_latest_marker_comment(comments, MARKER_FORMAL_DIAGNOSE)
    if latest_formal_diagnose is None:
        raise WorkflowError("Formal review-plan requires a latest wf:formal-diagnose comment.")

    diagnose_body = str(latest_formal_diagnose.get("body", "")).strip()
    diagnose_run_id = extract_comment_field(diagnose_body, "Backend Run ID")
    if not diagnose_run_id:
        raise WorkflowError("wf:formal-diagnose comment is missing Backend Run ID.")

    matching_backend_runs = [
        comment
        for comment in comments
        if MARKER_BACKEND_RUN in str(comment.get("body", ""))
        and extract_comment_field(str(comment.get("body", "")).strip(), "Run Id") == diagnose_run_id
    ]
    if not matching_backend_runs:
        raise WorkflowError(
            "Formal review-plan requires a wf:backend-run comment matching the diagnose Backend Run ID."
        )
    latest_backend_run = max(matching_backend_runs, key=comment_timestamp)

    return "\n\n".join(
        [
            indent_block(
                "Latest Backend Run Comment",
                truncate_text(str(latest_backend_run.get("body", "")).strip(), 8000),
            ),
            indent_block(
                "Latest Formal Diagnose Comment",
                truncate_text(diagnose_body, 12000),
            ),
        ]
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments used by GitHub Actions."""
    parser = argparse.ArgumentParser(description="Run the phase-2A Formal review-plan workflow.")
    parser.add_argument("pr_number", type=int, nargs="?", help="Pull request number.")
    return parser.parse_args()


def main() -> int:
    """Entry point for formal-review-plan.yml."""
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
        if current_state != "wf:backend-failed":
            print("Skipping formal review-plan because the PR is not in wf:backend-failed.")
            return 0

        prompt = load_formal_review_plan_context(pr_number, client)
        payload, response_id = call_openai_json(
            openai_config,
            build_formal_review_plan_instructions(),
            prompt,
        )
        rendered = normalize_formal_review_plan_payload(payload)
        body = f"{rendered.body}\n\n- OpenAI Response Id: `{response_id}`"
        client.create_marker_comment(pr_number, rendered.marker, body)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
