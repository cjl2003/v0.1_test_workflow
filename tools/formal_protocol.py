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
    context: str,
    current_stop_point: str,
    what_was_tried: Iterable[str],
    strongest_evidence: Iterable[str],
    key_logs_or_paths: Iterable[str],
    ruled_out: Iterable[str],
    candidate_next_step: str,
    questions_for_gpt: Iterable[str],
) -> str:
    return render_marked_comment(
        MARKER_FORMAL_DIAGNOSE,
        "Formal Diagnose",
        [],
        [
            ("Context", context),
            ("Current Stop Point", current_stop_point),
            ("What Was Tried", _clean_items(what_was_tried)),
            ("Strongest Evidence", _clean_items(strongest_evidence)),
            ("Key Logs / Paths", _clean_items(key_logs_or_paths)),
            ("Ruled Out", _clean_items(ruled_out)),
            ("Candidate Next Step", candidate_next_step),
            ("Questions For GPT", _clean_items(questions_for_gpt)),
        ],
    )


def render_formal_review_plan_comment(
    *,
    reason: str,
    next_plan: str,
    success_criteria: str,
    do_not_do: Iterable[str],
) -> str:
    return render_marked_comment(
        MARKER_FORMAL_REVIEW_PLAN,
        "Formal Review Plan",
        [("Decision", "formal-review-plan")],
        [
            ("Reason", reason),
            ("Next Plan", next_plan),
            ("Success Criteria", success_criteria),
            ("Do Not Do", _clean_items(do_not_do)),
        ],
    )


def render_formal_approval_comment(plan_title: str) -> str:
    approved_title = str(plan_title).strip() or "(untitled)"
    return render_marked_comment(
        MARKER_FORMAL_APPROVAL,
        "Formal Approval",
        [
            ("Source", "latest wf:formal-review-plan"),
            ("Channel", "desktop user via Codex relay"),
        ],
        [
            ("Approved Plan Title", approved_title),
            (
                "Approval Note",
                "Approved for execution from the latest wf:formal-review-plan via desktop user via Codex relay.",
            ),
        ],
    )
