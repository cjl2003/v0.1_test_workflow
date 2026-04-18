import unittest
from unittest import mock

from tools.formal_review_plan import (
    load_formal_review_plan_context,
    normalize_formal_review_plan_payload,
)
from tools.workflow_lib import WorkflowError


class FormalReviewPlanTests(unittest.TestCase):
    def test_load_formal_review_plan_context_uses_backend_run_referenced_by_diagnose(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            {
                "body": "<!-- wf:backend-run -->\n- Run Id: `phase2a-run-a`\nbackend run A",
                "created_at": "2026-04-18T10:00:00Z",
                "updated_at": "2026-04-18T10:00:00Z",
            },
            {
                "body": (
                    "<!-- wf:formal-diagnose -->\n"
                    "### Context\n"
                    "- Backend Run ID: `phase2a-run-a`\n"
                    "formal diagnose summary"
                ),
                "created_at": "2026-04-18T10:05:00Z",
                "updated_at": "2026-04-18T10:05:00Z",
            },
            {
                "body": "<!-- wf:backend-run -->\n- Run Id: `phase2a-run-b`\nbackend run B",
                "created_at": "2026-04-18T10:10:00Z",
                "updated_at": "2026-04-18T10:10:00Z",
            },
        ]

        prompt = load_formal_review_plan_context(20, client)

        self.assertIn("backend run A", prompt)
        self.assertNotIn("backend run B", prompt)

    def test_load_formal_review_plan_context_truncates_large_backend_run_comment(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            {
                "body": (
                    "<!-- wf:backend-run -->\n"
                    "- Run Id: `phase2a-run-a`\n"
                    + ("backend run detail\n" * 600)
                ),
                "created_at": "2026-04-18T10:00:00Z",
                "updated_at": "2026-04-18T10:00:00Z",
            },
            {
                "body": (
                    "<!-- wf:formal-diagnose -->\n"
                    "### Context\n"
                    "- Backend Run ID: `phase2a-run-a`\n"
                    "formal diagnose summary"
                ),
                "created_at": "2026-04-18T10:05:00Z",
                "updated_at": "2026-04-18T10:05:00Z",
            },
        ]

        prompt = load_formal_review_plan_context(20, client)

        self.assertIn("[truncated by workflow_lib.py to keep prompt size bounded]", prompt)

    def test_load_formal_review_plan_context_uses_latest_backend_run_and_diagnose(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            {
                "body": "<!-- wf:backend-run -->\n- Run Id: `phase2a-run-a`\nbackend run summary",
                "created_at": "2026-04-18T10:00:00Z",
                "updated_at": "2026-04-18T10:00:00Z",
            },
            {
                "body": (
                    "<!-- wf:formal-diagnose -->\n"
                    "### Context\n"
                    "- Backend Run ID: `phase2a-run-a`\n"
                    "formal diagnose summary"
                ),
                "created_at": "2026-04-18T10:05:00Z",
                "updated_at": "2026-04-18T10:05:00Z",
            },
        ]

        prompt = load_formal_review_plan_context(20, client)

        self.assertIn("Latest Backend Run Comment", prompt)
        self.assertIn("backend run summary", prompt)
        self.assertIn("Latest Formal Diagnose Comment", prompt)
        self.assertIn("formal diagnose summary", prompt)

    def test_load_formal_review_plan_context_requires_backend_run_and_diagnose(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            {
                "body": "<!-- wf:backend-run -->\nbackend run summary",
                "created_at": "2026-04-18T10:00:00Z",
                "updated_at": "2026-04-18T10:00:00Z",
            }
        ]

        with self.assertRaises(WorkflowError):
            load_formal_review_plan_context(20, client)

    def test_normalize_formal_review_plan_payload_rejects_non_list_reasons(self) -> None:
        with self.assertRaises(WorkflowError):
            normalize_formal_review_plan_payload(
                {
                    "decision": "approve",
                    "reasons": "not-a-list",
                    "next_plan": {
                        "title": "Narrow proof to one compare point",
                        "hypothesis": "The blocker is isolated to mode0_prev_product_28 only.",
                        "one_experiment": "Run one targeted proof for that point.",
                        "expected_evidence": "Either the point proves or a stable counterexample appears.",
                        "stop_condition": "Stop after the single targeted proof completes.",
                    },
                    "success_criteria": "The broad undet cluster claim is replaced by a single-point conclusion.",
                    "do_not_do": ["Do not restart broad observable-cluster proofs."],
                }
            )

    def test_normalize_formal_review_plan_payload_rejects_null_reasons(self) -> None:
        with self.assertRaises(WorkflowError):
            normalize_formal_review_plan_payload(
                {
                    "decision": "approve",
                    "reasons": None,
                    "next_plan": {
                        "title": "Narrow proof to one compare point",
                        "hypothesis": "The blocker is isolated to mode0_prev_product_28 only.",
                        "one_experiment": "Run one targeted proof for that point.",
                        "expected_evidence": "Either the point proves or a stable counterexample appears.",
                        "stop_condition": "Stop after the single targeted proof completes.",
                    },
                    "success_criteria": "The broad undet cluster claim is replaced by a single-point conclusion.",
                    "do_not_do": ["Do not restart broad observable-cluster proofs."],
                }
            )

    def test_normalize_formal_review_plan_payload_for_approve(self) -> None:
        rendered = normalize_formal_review_plan_payload(
            {
                "decision": "approve",
                "reasons": ["The current diagnosis is supported by the evidence."],
                "next_plan": {
                    "title": "Narrow proof to one compare point",
                    "hypothesis": "The blocker is isolated to mode0_prev_product_28 only.",
                    "one_experiment": "Run one targeted proof for that point.",
                    "expected_evidence": "Either the point proves or a stable counterexample appears.",
                    "stop_condition": "Stop after the single targeted proof completes.",
                },
                "success_criteria": "The broad undet cluster claim is replaced by a single-point conclusion.",
                "do_not_do": ["Do not restart broad observable-cluster proofs."],
            }
        )

        self.assertEqual(rendered.marker, "<!-- wf:formal-review-plan -->")
        self.assertEqual(rendered.target_state, "wf:backend-failed")
        self.assertIn("Decision: `approve`", rendered.body)
        self.assertIn("Narrow proof to one compare point", rendered.body)

    def test_normalize_formal_review_plan_payload_for_reject(self) -> None:
        rendered = normalize_formal_review_plan_payload(
            {
                "decision": "reject",
                "reasons": ["The diagnosis does not yet rule out an observability issue."],
                "next_plan": {
                    "title": "Add one observability-focused check",
                    "hypothesis": "The current evidence is still too indirect.",
                    "one_experiment": "Capture one output-path check tied to the compare point.",
                    "expected_evidence": "The new check confirms or rejects the current conclusion.",
                    "stop_condition": "Stop after one observability experiment.",
                },
                "success_criteria": "One new log closes the current evidence gap.",
                "do_not_do": ["Do not start a new RTL change direction."],
            }
        )

        self.assertEqual(rendered.marker, "<!-- wf:formal-review-plan -->")
        self.assertEqual(rendered.target_state, "wf:backend-failed")
        self.assertIn("Decision: `reject`", rendered.body)
        self.assertIn("Add one observability-focused check", rendered.body)

    def test_normalize_formal_review_plan_payload_rejects_invalid_decision(self) -> None:
        with self.assertRaises(WorkflowError):
            normalize_formal_review_plan_payload(
                {
                    "decision": "maybe",
                    "reasons": ["The diagnosis is not specific enough yet."],
                    "next_plan": {
                        "title": "Add one observability-focused check",
                        "hypothesis": "The current evidence is still too indirect.",
                        "one_experiment": "Capture one output-path check tied to the compare point.",
                        "expected_evidence": "The new check confirms or rejects the current conclusion.",
                        "stop_condition": "Stop after one observability experiment.",
                    },
                    "success_criteria": "One new log closes the current evidence gap.",
                    "do_not_do": ["Do not start a new RTL change direction."],
                }
            )


if __name__ == "__main__":
    unittest.main()
