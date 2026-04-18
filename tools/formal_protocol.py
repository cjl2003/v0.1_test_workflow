#!/usr/bin/env python3
"""Shared render helpers for the phase-2A lightweight Formal subloop."""

from __future__ import annotations

from typing import Iterable

from tools.workflow_lib import (
    MARKER_FORMAL_APPROVAL,
    MARKER_FORMAL_DIAGNOSE,
    MARKER_FORMAL_REVIEW_PLAN,
    WorkflowError,
    render_marked_comment,
)


def _clean_items(items: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        if item is None:
            continue
        value = str(item).strip()
        if value:
            cleaned.append(value)
    return cleaned


def _clean_attempts(items: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    cleaned: list[tuple[str, str]] = []
    for name, result in items:
        if name is None or result is None:
            continue
        cleaned_name = str(name).strip()
        cleaned_result = str(result).strip()
        if not cleaned_name or not cleaned_result:
            continue
        cleaned.append((cleaned_name, cleaned_result))
    return cleaned


def _require_non_empty(value: str, field_name: str) -> str:
    if value is None:
        raise WorkflowError(f"Formal review-plan field {field_name} must be non-empty.")
    cleaned = str(value).strip()
    if not cleaned:
        raise WorkflowError(f"Formal review-plan field {field_name} must be non-empty.")
    return cleaned


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
    cleaned_backend_run_id = _require_non_empty(backend_run_id, "backend_run_id")
    cleaned_commit_ref = _require_non_empty(commit_ref, "commit_ref")
    cleaned_formal_status = _require_non_empty(formal_status, "formal_status")
    cleaned_current_stop_point = _require_non_empty(
        current_stop_point, "current_stop_point"
    )
    cleaned_current_leaning = ""
    if current_leaning is not None:
        cleaned_current_leaning = str(current_leaning).strip()
    cleaned_compare_points = _clean_items(affected_compare_points)
    cleaned_attempts = _clean_attempts(attempts)
    cleaned_evidence_paths = _clean_items(evidence_paths)
    context_lines = [
        f"PR: `{pr_number}`",
        f"Backend Run ID: `{cleaned_backend_run_id}`",
        f"Commit / Ref: `{cleaned_commit_ref}`",
        f"Formal Status: `{cleaned_formal_status}`",
        "Affected Compare Point(s): "
        + (", ".join(f"`{item}`" for item in cleaned_compare_points) or "_None_"),
    ]
    next_step_lines = _clean_items(candidate_next_steps)
    if cleaned_current_leaning:
        next_step_lines.append(f"Current Leaning: {cleaned_current_leaning}")
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
            ("Current Stop Point", cleaned_current_stop_point),
            (
                "What Was Tried",
                [f"{name}: {result}" for name, result in cleaned_attempts] or ["None."],
            ),
            ("Strongest Evidence", _clean_items(strongest_evidence)),
            ("Key Logs / Paths", [f"`{item}`" for item in cleaned_evidence_paths]),
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
    normalized_decision = str(decision).strip().lower()
    if normalized_decision not in {"approve", "reject", "revise"}:
        raise WorkflowError(
            "Formal review-plan decision must be one of: approve, reject, revise."
        )

    cleaned_reasons = _clean_items(reasons)
    cleaned_plan_title = _require_non_empty(plan_title, "plan_title")
    cleaned_hypothesis = _require_non_empty(hypothesis, "hypothesis")
    cleaned_one_experiment = _require_non_empty(one_experiment, "one_experiment")
    cleaned_expected_evidence = _require_non_empty(expected_evidence, "expected_evidence")
    cleaned_stop_condition = _require_non_empty(stop_condition, "stop_condition")
    cleaned_success_criteria = _require_non_empty(success_criteria, "success_criteria")
    cleaned_do_not_do = _clean_items(do_not_do)

    return render_marked_comment(
        MARKER_FORMAL_REVIEW_PLAN,
        "Phase-2A Formal Review Plan",
        [("Decision", normalized_decision)],
        [
            ("Reason", cleaned_reasons),
            (
                "Next Plan",
                [
                    f"Plan Title: {cleaned_plan_title}",
                    f"Hypothesis: {cleaned_hypothesis}",
                    f"One Experiment / One Fix Direction: {cleaned_one_experiment}",
                    f"Expected Evidence: {cleaned_expected_evidence}",
                    f"Stop Condition: {cleaned_stop_condition}",
                ],
            ),
            ("Success Criteria", cleaned_success_criteria),
            ("Do Not Do", cleaned_do_not_do),
        ],
    )


def render_formal_approval_comment(plan_title: str) -> str:
    approved_title = _require_non_empty(plan_title, "plan_title")
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
