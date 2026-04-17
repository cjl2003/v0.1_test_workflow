#!/usr/bin/env python3
"""Generate a phase-1 clarification or plan comment for a request PR."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any

from tools.workflow_lib import (
    GitHubClient,
    MARKER_CLARIFICATION,
    MARKER_PLAN,
    RenderedComment,
    WorkflowError,
    call_openai_json,
    extract_primary_state,
    find_request_document,
    get_env,
    indent_block,
    load_github_config,
    load_openai_config,
    read_text_file,
    render_marked_comment,
    truncate_text,
)


def normalize_planner_payload(payload: dict[str, Any]) -> RenderedComment:
    """Turn model JSON into the canonical machine-readable PR comment."""
    decision = str(payload.get("decision", "")).strip().lower()

    if decision == "plan":
        summary = str(payload.get("summary", "")).strip()
        tasks = [str(item).strip() for item in payload.get("tasks", []) if str(item).strip()]
        file_touches = [
            str(item).strip() for item in payload.get("file_touches", []) if str(item).strip()
        ]
        done_definition = [
            str(item).strip()
            for item in payload.get("done_definition", [])
            if str(item).strip()
        ]

        if not summary or not tasks or not file_touches or not done_definition:
            raise WorkflowError("Planner JSON for decision=plan is missing required sections.")

        body = render_marked_comment(
            MARKER_PLAN,
            "Frontend Plan",
            [("Decision", "plan")],
            [
                ("Plan Summary", summary),
                ("Ordered Task List", tasks),
                ("Expected File Touch List", [f"`{item}`" for item in file_touches]),
                ("Done Definition", done_definition),
            ],
        )
        return RenderedComment(MARKER_PLAN, "wf:awaiting-plan-approval", body)

    if decision == "clarification":
        blocking_reason = str(payload.get("blocking_reason", "")).strip()
        questions = [
            str(item).strip() for item in payload.get("questions", []) if str(item).strip()
        ]

        if not blocking_reason or not questions:
            raise WorkflowError(
                "Planner JSON for decision=clarification is missing blocking_reason or questions."
            )

        body = render_marked_comment(
            MARKER_CLARIFICATION,
            "Frontend Clarification",
            [("Decision", "clarification")],
            [
                ("Blocking Reason", blocking_reason),
                ("Questions", questions),
            ],
        )
        return RenderedComment(MARKER_CLARIFICATION, "wf:needs-clarification", body)

    raise WorkflowError(f"Unsupported planner decision: {decision!r}")


def build_planner_instructions() -> str:
    """High-priority instructions for the request planning model."""
    return textwrap.dedent(
        """
        You are the GitHub-side planner in a phase-1 PR-driven RTL frontend workflow.
        Follow the repository spec exactly. Do not redesign architecture, do not introduce
        phase-2 behavior, and do not expand scope beyond the current request.

        Decide between exactly two outcomes:
        1. "clarification" when the request is still ambiguous enough to block safe planning.
        2. "plan" when the request is clear enough for local Codex execution.

        Rules:
        - Use only the provided request document, repository docs, prior clarification comments,
          and /answer comments.
        - Never guess a plan when a blocking ambiguity remains.
        - Keep clarification questions minimal and directly blocking.
        - A plan must stay inside phase-1: no auto-replan, no auto-rerun, no backend expansion.
        - Return JSON only.

        JSON shape:
        For clarification:
        {
          "decision": "clarification",
          "blocking_reason": "short sentence",
          "questions": ["question 1", "question 2"]
        }

        For plan:
        {
          "decision": "plan",
          "summary": "short paragraph",
          "tasks": ["task 1", "task 2"],
          "file_touches": ["path/to/file"],
          "done_definition": ["definition 1", "definition 2"]
        }
        """
    ).strip()


def collect_answer_comments(comments: list[dict[str, Any]]) -> list[str]:
    """Collect `/answer ...` user replies in chronological order."""
    answers: list[tuple[str, str]] = []
    for comment in comments:
        body = str(comment.get("body", "")).strip()
        if not body.startswith("/answer"):
            continue
        answers.append((str(comment.get("created_at", "")), body))
    return [body for _, body in sorted(answers)]


def load_request_context(pr_number: int, client: GitHubClient) -> str:
    """Build the planner prompt from the checked-out repo plus PR comments."""
    comments = client.list_issue_comments(pr_number)
    pr_files = client.list_pull_request_files(pr_number)
    request_path = find_request_document(pr_files)
    if request_path is None:
        raise WorkflowError(
            "No docs/requests/*.md file was found in the pull request. "
            "Submitter must create a request document first."
        )

    request_doc = read_text_file(request_path)
    repo_spec = read_text_file(Path("docs/spec.md"))
    golden_vectors = read_text_file(Path("docs/golden_vectors.md"))

    clarification_comments = [
        str(comment.get("body", "")).strip()
        for comment in comments
        if MARKER_CLARIFICATION in str(comment.get("body", ""))
    ]
    answers = collect_answer_comments(comments)

    blocks = [
        indent_block("Request Document", truncate_text(request_doc, 20000)),
        indent_block("docs/spec.md", truncate_text(repo_spec, 16000)),
        indent_block("docs/golden_vectors.md", truncate_text(golden_vectors, 4000)),
        indent_block(
            "Prior Clarification Comments",
            "\n\n".join(clarification_comments) if clarification_comments else "(none)",
        ),
        indent_block("User /answer Comments", "\n".join(answers) if answers else "(none)"),
    ]
    return "\n\n".join(blocks)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments used by GitHub Actions."""
    parser = argparse.ArgumentParser(description="Publish a plan or clarification comment.")
    parser.add_argument("pr_number", type=int, nargs="?", help="Pull request number.")
    return parser.parse_args()


def main() -> int:
    """Entry point for `request-plan.yml`."""
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
        event_name = get_env("GITHUB_EVENT_NAME", "")
        if event_name == "issue_comment" and current_state not in {
            "wf:intake",
            "wf:needs-clarification",
        }:
            print(
                "Skipping request planning because the PR is not in "
                "wf:intake or wf:needs-clarification."
            )
            return 0

        prompt = load_request_context(pr_number, client)
        payload, response_id = call_openai_json(
            openai_config, build_planner_instructions(), prompt
        )
        rendered = normalize_planner_payload(payload)

        body = f"{rendered.body}\n\n- OpenAI Response Id: `{response_id}`"
        client.ensure_primary_labels_exist()
        client.upsert_marker_comment(pr_number, rendered.marker, body)
        client.set_primary_state(pr_number, rendered.target_state)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
