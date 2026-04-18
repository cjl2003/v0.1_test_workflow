#!/usr/bin/env python3
"""Shared render helpers for the phase-2A lightweight Formal subloop."""

from __future__ import annotations

from typing import Iterable

from tools.workflow_lib import (
    MARKER_FORMAL_APPROVAL,
    MARKER_FORMAL_DIAGNOSE,
    MARKER_FORMAL_REVIEW_PLAN,
    render_marked_comment,
)


def _clean_items(items: Iterable[str]) -> list[str]:
    return [str(item).strip() for item in items if str(item).strip()]


def render_formal_diagnose_comment(
    *,
    pr_number: int,
    backend_run_id: str,
    commit_ref: str,
    formal_status: str,
    affected_compare_points: list[str],
    current_stop_point: str,
    attempts: list[tuple[str, str]],
    strongest_evidence: list[str],
    evidence_paths: list[str],
    ruled_out: list[str],
    candidate_next_steps: list[str],
    current_leaning: str,
) -> str:
    context_lines = [
        f"PR: `{pr_number}`",
        f"Backend Run ID: `{backend_run_id}`",
        f"Commit / Ref: `{commit_ref}`",
        f"Formal Status: `{formal_status}`",
        "Affected Compare Point(s): "
        + (", ".join(f"`{item}`" for item in affected_compare_points) or "_None_"),
    ]
    next_step_lines = _clean_items(candidate_next_steps)
    if current_leaning.strip():
        next_step_lines.append(f"Current Leaning: {current_leaning.strip()}")
    questions = [
        "What is the single best next formal step?",
        "What evidence should be gathered or tightened next?",
        "What should not be done yet?",
    ]
    return render_marked_comment(
        MARKER_FORMAL_DIAGNOSE,
        "Phase-2A Formal Diagnose",
        [],
        [
            ("Context", context_lines),
            ("Current Stop Point", current_stop_point),
            (
                "What Was Tried",
                [f"{name}: {result}" for name, result in attempts] or ["None."],
            ),
            ("Strongest Evidence", _clean_items(strongest_evidence)),
            ("Key Logs / Paths", [f"`{item}`" for item in evidence_paths]),
            ("Ruled Out", _clean_items(ruled_out)),
            ("Candidate Next Step", next_step_lines or ["None."]),
            ("Questions For GPT", questions),
        ],
    )


def render_formal_review_plan_comment(
    *,
    decision: str,
    reasons: list[str],
    plan_title: str,
    hypothesis: str,
    one_experiment: str,
    expected_evidence: str,
    stop_condition: str,
    success_criteria: str,
    do_not_do: list[str],
) -> str:
    return render_marked_comment(
        MARKER_FORMAL_REVIEW_PLAN,
        "Phase-2A Formal Review Plan",
        [("Decision", decision)],
        [
            ("Reason", _clean_items(reasons)),
            (
                "Next Plan",
                [
                    f"Plan Title: {plan_title}",
                    f"Hypothesis: {hypothesis}",
                    f"One Experiment / One Fix Direction: {one_experiment}",
                    f"Expected Evidence: {expected_evidence}",
                    f"Stop Condition: {stop_condition}",
                ],
            ),
            ("Success Criteria", success_criteria),
            ("Do Not Do", _clean_items(do_not_do)),
        ],
    )


def render_formal_approval_comment(plan_title: str) -> str:
    approved_title = str(plan_title).strip() or "(untitled)"
    return render_marked_comment(
        MARKER_FORMAL_APPROVAL,
        "Phase-2A Formal Approval",
        [
            ("Approved Source", "latest wf:formal-review-plan"),
            ("Approved By", "desktop user via Codex relay"),
        ],
        [
            ("Approved Plan", approved_title),
            (
                "Approval Note",
                "Approved for execution from the latest wf:formal-review-plan via desktop user via Codex relay.",
            ),
        ],
    )
