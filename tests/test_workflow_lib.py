import unittest
from pathlib import Path

from tools.command_router import evaluate_command
from tools.frontend_review import normalize_review_payload
from tools.request_planner import normalize_planner_payload
from tools.workflow_lib import (
    PRIMARY_LABELS,
    build_primary_label_set,
    find_latest_marker_comment,
)


def make_comment(body: str, created_at: str, updated_at: str | None = None) -> dict:
    return {
        "body": body,
        "created_at": created_at,
        "updated_at": updated_at or created_at,
    }


class WorkflowLabelTests(unittest.TestCase):
    def test_build_primary_label_set_replaces_existing_primary_label(self) -> None:
        labels = ["bug", "wf:intake", "docs"]

        updated = build_primary_label_set(labels, "wf:codex-queued")

        self.assertEqual(
            updated,
            ["bug", "docs", "wf:codex-queued"],
        )

    def test_primary_labels_constant_contains_phase1_states(self) -> None:
        self.assertEqual(
            PRIMARY_LABELS,
            (
                "wf:intake",
                "wf:needs-clarification",
                "wf:awaiting-plan-approval",
                "wf:codex-queued",
                "wf:codex-running",
                "wf:awaiting-gpt-review",
                "wf:rework-needed",
                "wf:frontend-passed",
                "wf:failed",
            ),
        )

    def test_find_latest_marker_comment_prefers_updated_timestamp(self) -> None:
        comments = [
            make_comment(
                "<!-- wf:plan -->\nold plan",
                "2026-04-17T00:00:00Z",
                "2026-04-17T00:00:00Z",
            ),
            make_comment(
                "<!-- wf:plan -->\nnew plan",
                "2026-04-17T00:01:00Z",
                "2026-04-17T00:05:00Z",
            ),
        ]

        latest = find_latest_marker_comment(comments, "<!-- wf:plan -->")

        self.assertIsNotNone(latest)
        self.assertIn("new plan", latest["body"])


class CommandRouterTests(unittest.TestCase):
    def test_approve_plan_requires_newer_comment_than_latest_plan(self) -> None:
        result = evaluate_command(
            command="/approve-plan",
            current_state="wf:awaiting-plan-approval",
            author_association="MEMBER",
            command_created_at="2026-04-17T00:03:00Z",
            latest_plan_updated_at="2026-04-17T00:04:00Z",
            latest_gpt_review_updated_at=None,
        )

        self.assertFalse(result.accepted)
        self.assertIn("latest wf:plan", result.reason)

    def test_approve_plan_moves_to_codex_queue_when_valid(self) -> None:
        result = evaluate_command(
            command="/approve-plan",
            current_state="wf:awaiting-plan-approval",
            author_association="OWNER",
            command_created_at="2026-04-17T00:05:00Z",
            latest_plan_updated_at="2026-04-17T00:04:00Z",
            latest_gpt_review_updated_at=None,
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.target_state, "wf:codex-queued")

    def test_codex_fix_requires_rework_state_and_latest_review(self) -> None:
        result = evaluate_command(
            command="/codex-fix",
            current_state="wf:rework-needed",
            author_association="COLLABORATOR",
            command_created_at="2026-04-17T00:07:00Z",
            latest_plan_updated_at=None,
            latest_gpt_review_updated_at=None,
        )

        self.assertFalse(result.accepted)
        self.assertIn("wf:gpt-review", result.reason)

    def test_codex_fix_requeues_minimal_repair_round(self) -> None:
        result = evaluate_command(
            command="/codex-fix",
            current_state="wf:rework-needed",
            author_association="COLLABORATOR",
            command_created_at="2026-04-17T00:08:00Z",
            latest_plan_updated_at="2026-04-17T00:04:00Z",
            latest_gpt_review_updated_at="2026-04-17T00:07:00Z",
        )

        self.assertTrue(result.accepted)
        self.assertEqual(result.target_state, "wf:codex-queued")


class PlannerPayloadTests(unittest.TestCase):
    def test_normalize_planner_payload_for_plan_comment(self) -> None:
        normalized = normalize_planner_payload(
            {
                "decision": "plan",
                "summary": "Implement MAC16 phase-1 frontend work.",
                "tasks": [
                    "Update rtl/mac16.sv for mode switch semantics.",
                    "Adjust tb/tb_mac16.sv checks to match golden vectors.",
                ],
                "file_touches": ["rtl/mac16.sv", "tb/tb_mac16.sv"],
                "done_definition": [
                    "sim/run_iverilog.bat succeeds.",
                    "python tools/check_golden.py succeeds.",
                ],
            }
        )

        self.assertEqual(normalized.marker, "<!-- wf:plan -->")
        self.assertEqual(normalized.target_state, "wf:awaiting-plan-approval")
        self.assertIn("Plan Summary", normalized.body)

    def test_normalize_planner_payload_for_clarification_comment(self) -> None:
        normalized = normalize_planner_payload(
            {
                "decision": "clarification",
                "questions": [
                    "Which branch should be the base branch for this request?",
                ],
                "blocking_reason": "Base branch is not stated in the request document.",
            }
        )

        self.assertEqual(normalized.marker, "<!-- wf:clarification -->")
        self.assertEqual(normalized.target_state, "wf:needs-clarification")
        self.assertIn("Blocking Reason", normalized.body)


class FrontendReviewPayloadTests(unittest.TestCase):
    def test_normalize_review_payload_for_pass(self) -> None:
        normalized = normalize_review_payload(
            {
                "outcome": "pass",
                "summary": "Frontend verification and review both pass.",
                "findings": [],
                "next_checks": ["Monitor downstream backend stages manually."],
            }
        )

        self.assertEqual(normalized.target_state, "wf:frontend-passed")
        self.assertIn("Outcome: `pass`", normalized.body)

    def test_normalize_review_payload_for_rework(self) -> None:
        normalized = normalize_review_payload(
            {
                "outcome": "rework-needed",
                "summary": "Mode switch path still mishandles buffered frames.",
                "findings": [
                    "[P1] rtl/mac16.sv - old-mode drain finishes after new-mode output starts.",
                ],
                "next_checks": ["Keep the repair limited to the latest review issue."],
            }
        )

        self.assertEqual(normalized.target_state, "wf:rework-needed")
        self.assertIn("Outcome: `rework-needed`", normalized.body)


class WorkflowFilesTests(unittest.TestCase):
    def test_workflows_use_node24_compatible_action_versions(self) -> None:
        workflow_dir = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        workflow_files = (
            workflow_dir / "command-router.yml",
            workflow_dir / "frontend-review.yml",
            workflow_dir / "request-plan.yml",
        )

        for workflow_file in workflow_files:
            content = workflow_file.read_text(encoding="utf-8")
            self.assertIn("uses: actions/checkout@v6", content)
            self.assertIn("uses: actions/setup-python@v6", content)


if __name__ == "__main__":
    unittest.main()
