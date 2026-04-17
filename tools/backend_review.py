#!/usr/bin/env python3
"""Run the GitHub-side GPT backend review for a completed phase-2A run."""

from __future__ import annotations

import argparse
import textwrap
from typing import Any

from tools.backend_baseline import render_phase2a_review_comment
from tools.workflow_lib import (
    GitHubClient,
    MARKER_BACKEND_REVIEW,
    MARKER_BACKEND_RUN,
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
    truncate_text,
)


def normalize_backend_review_payload(payload: dict[str, Any]) -> RenderedComment:
    """Normalize the model JSON into the canonical phase-2A backend review comment."""
    outcome = str(payload.get("outcome", "")).strip().lower()
    summary = str(payload.get("summary", "")).strip()
    hard_findings = [
        str(item).strip() for item in payload.get("hard_findings", []) if str(item).strip()
    ]
    baseline_warnings = [
        str(item).strip()
        for item in payload.get("baseline_warnings", [])
        if str(item).strip()
    ]
    next_gate_recommendation = str(payload.get("next_gate_recommendation", "")).strip()

    if outcome not in {"pass", "failed"}:
        raise WorkflowError(f"Unsupported backend review outcome: {outcome!r}")
    if not summary:
        raise WorkflowError("Backend review payload must include a non-empty summary.")
    if not next_gate_recommendation:
        raise WorkflowError("Backend review payload must include next_gate_recommendation.")

    body = render_phase2a_review_comment(
        outcome=outcome,
        summary=summary,
        hard_findings=hard_findings,
        baseline_warnings=baseline_warnings,
        next_gate_recommendation=next_gate_recommendation,
    )
    target_state = "wf:backend-passed" if outcome == "pass" else "wf:backend-failed"
    return RenderedComment(MARKER_BACKEND_REVIEW, target_state, body)


def build_backend_review_instructions() -> str:
    """High-priority instructions for the phase-2A backend review model."""
    return textwrap.dedent(
        """
        You are the GitHub-side GPT-5.4 reviewer for phase-2A backend baseline runs.
        Review only whether the latest backend baseline satisfies the phase-2A gate.

        Rules:
        - You must return exactly one outcome: "pass" or "failed".
        - Hard pass requires synthesis success, mapped netlist generation, constraint loading, Formal EC success, and required baseline artifacts.
        - You may include baseline warnings for synthesis power, area, or timing, but do not propose or launch an optimization loop here.
        - Stay inside phase-2A. Do not expand into P&R, signoff STA, LVS, SPEF, or phase-2B planning.
        - Return JSON only.

        JSON shape:
        {
          "outcome": "pass" | "failed",
          "summary": "short paragraph",
          "hard_findings": ["finding 1", "finding 2"],
          "baseline_warnings": ["warning 1", "warning 2"],
          "next_gate_recommendation": "ready-for-phase-2b" | "revise-rtl-before-phase-2b"
        }
        """
    ).strip()


def load_backend_review_context(pr_number: int, client: GitHubClient) -> str:
    """Build the backend review prompt from the latest phase-2A run artifacts."""
    comments = client.list_issue_comments(pr_number)
    latest_run = find_latest_marker_comment(comments, MARKER_BACKEND_RUN)
    if latest_run is None:
        raise WorkflowError("Cannot run backend review without a latest wf:backend-run comment.")

    run_body = str(latest_run.get("body", "")).strip()
    repo_artifact_dir = extract_comment_field(run_body, "Repo Artifact Dir")
    if not repo_artifact_dir:
        raise WorkflowError("wf:backend-run comment is missing Repo Artifact Dir.")

    summary_doc = client.fetch_pull_request_file_text(pr_number, f"{repo_artifact_dir}/summary.md")
    manifest_json = client.fetch_pull_request_file_text(
        pr_number, f"{repo_artifact_dir}/manifest.json"
    )
    formal_summary = client.fetch_pull_request_file_text(
        pr_number, f"{repo_artifact_dir}/reports/formal_ec_summary.md"
    )
    constraint_summary = client.fetch_pull_request_file_text(
        pr_number, f"{repo_artifact_dir}/reports/constraint_summary.md"
    )
    timing_summary = client.fetch_pull_request_file_text(
        pr_number, f"{repo_artifact_dir}/reports/synthesis_timing_summary.rpt"
    )
    area_report = client.fetch_pull_request_file_text(
        pr_number, f"{repo_artifact_dir}/reports/synthesis_area.rpt"
    )
    power_report = client.fetch_pull_request_file_text(
        pr_number, f"{repo_artifact_dir}/reports/synthesis_power.rpt"
    )

    blocks = [
        indent_block("Latest Backend Run Comment", run_body),
        indent_block("Backend Summary Document", truncate_text(summary_doc, 12000)),
        indent_block("Backend Manifest", truncate_text(manifest_json, 8000)),
        indent_block("Formal EC Summary", truncate_text(formal_summary, 8000)),
        indent_block("Constraint Summary", truncate_text(constraint_summary, 8000)),
        indent_block("Timing Summary", truncate_text(timing_summary, 8000)),
        indent_block("Area Report", truncate_text(area_report, 8000)),
        indent_block("Power Report", truncate_text(power_report, 8000)),
    ]
    return "\n\n".join(blocks)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments used by GitHub Actions."""
    parser = argparse.ArgumentParser(description="Run the phase-2A backend baseline review.")
    parser.add_argument("pr_number", type=int, nargs="?", help="Pull request number.")
    return parser.parse_args()


def main() -> int:
    """Entry point for `backend-review.yml`."""
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
        if current_state != "wf:awaiting-backend-review":
            print(
                "Skipping backend review because the PR is not in wf:awaiting-backend-review."
            )
            return 0

        prompt = load_backend_review_context(pr_number, client)
        payload, response_id = call_openai_json(
            openai_config, build_backend_review_instructions(), prompt
        )
        rendered = normalize_backend_review_payload(payload)

        body = f"{rendered.body}\n\n- OpenAI Response Id: `{response_id}`"
        client.ensure_primary_labels_exist()
        client.upsert_marker_comment(pr_number, rendered.marker, body)
        client.set_primary_state(pr_number, rendered.target_state)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
