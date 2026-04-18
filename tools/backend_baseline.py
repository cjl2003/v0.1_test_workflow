#!/usr/bin/env python3
"""Shared helpers for phase-2A backend baseline artifacts and comments."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from tools.workflow_lib import (
    MARKER_BACKEND_REVIEW,
    MARKER_BACKEND_RUN,
    render_marked_comment,
)


def build_phase2a_run_id(timestamp_token: str, version: str) -> str:
    """Build a stable phase-2A run id."""
    return f"phase2a-{timestamp_token}-{version}"


def build_phase2a_tag(status_token: str, timestamp_token: str, version: str) -> str:
    """Build the normalized phase-2A tag."""
    return f"v0.1_phase2a_{status_token}_{timestamp_token}_{version}"


def build_phase2a_repo_dir(request_id: str, run_id: str) -> Path:
    """Return the repository artifact directory for one phase-2A run."""
    return Path("docs") / "runs" / request_id / "backend" / run_id


def build_phase2a_local_dir(request_id: str, run_id: str) -> Path:
    """Return the Windows-side local package directory for one phase-2A run."""
    return Path.home() / ".codex" / "backend_runs" / request_id / run_id


def _render_baseline_metric_lines(baseline_metrics: Mapping[str, str]) -> list[str]:
    labels = {
        "power": "Power",
        "area": "Area",
        "timing": "Timing",
    }
    lines: list[str] = []
    for key in ("power", "area", "timing"):
        value = str(baseline_metrics.get(key, "")).strip()
        if value:
            lines.append(f"{labels[key]}: `{value}`")
    return lines or ["No baseline metrics were captured."]


def render_phase2a_summary_document(
    request_id: str,
    run_id: str,
    version: str,
    tag: str,
    synthesis_status: str,
    mapped_netlist_status: str,
    constraints_status: str,
    formal_ec_status: str,
    baseline_metrics: Mapping[str, str],
    notes: str,
    commit_id: str = "pending",
) -> str:
    """Render the repository summary document for one phase-2A run."""
    metric_lines = _render_baseline_metric_lines(baseline_metrics)
    return (
        "# Phase-2A Backend Summary\n\n"
        f"- Request Id: `{request_id}`\n"
        f"- Run Id: `{run_id}`\n"
        f"- Version: `{version}`\n"
        f"- Tag: `{tag}`\n"
        f"- Commit: `{commit_id}`\n\n"
        "## Gate Status\n"
        f"- Synthesis: `{synthesis_status}`\n"
        f"- Mapped Netlist: `{mapped_netlist_status}`\n"
        f"- Constraints: `{constraints_status}`\n"
        f"- Formal EC: `{formal_ec_status}`\n\n"
        "## Baseline Metrics\n"
        + "\n".join(f"- {item}" for item in metric_lines)
        + f"\n\n## Short Notes\n{notes.strip()}\n"
    )


def render_phase2a_run_comment(
    status: str,
    run_id: str,
    commit_id: str | None,
    tag: str | None,
    local_package_dir: str,
    repo_artifact_dir: str,
    synthesis_status: str,
    mapped_netlist_status: str,
    constraints_status: str,
    formal_ec_status: str,
    baseline_metrics: Mapping[str, str],
    notes: str,
) -> str:
    """Render the machine-readable phase-2A backend run comment."""
    metadata = [
        ("Status", status),
        ("Run Id", run_id),
    ]
    if commit_id:
        metadata.append(("Commit", commit_id))
    if tag:
        metadata.append(("Tag", tag))
    metadata.extend(
        [
            ("Local Package Dir", local_package_dir),
            ("Repo Artifact Dir", repo_artifact_dir),
        ]
    )

    sections = [
        (
            "Gate Status",
            [
                f"Synthesis: `{synthesis_status}`",
                f"Mapped Netlist: `{mapped_netlist_status}`",
                f"Constraints: `{constraints_status}`",
                f"Formal EC: `{formal_ec_status}`",
            ],
        ),
        ("Baseline Metrics", _render_baseline_metric_lines(baseline_metrics)),
        ("Notes", notes.strip()),
    ]
    return render_marked_comment(
        MARKER_BACKEND_RUN,
        "Phase-2A Backend Run",
        metadata,
        sections,
    )


def render_phase2a_review_comment(
    outcome: str,
    summary: str,
    hard_findings: list[str],
    baseline_warnings: list[str],
    next_gate_recommendation: str,
) -> str:
    """Render the machine-readable phase-2A backend review comment."""
    sections = [
        ("Summary", summary.strip()),
        ("Hard Findings", hard_findings),
        ("Baseline Warnings", baseline_warnings),
        ("Next Gate Recommendation", f"`{next_gate_recommendation}`"),
    ]
    return render_marked_comment(
        MARKER_BACKEND_REVIEW,
        "Phase-2A Backend Review",
        [("Outcome", outcome)],
        sections,
    )
