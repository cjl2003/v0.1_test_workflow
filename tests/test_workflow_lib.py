import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.command_router import evaluate_command
from tools.frontend_review import normalize_review_payload
from tools.request_planner import normalize_planner_payload
import tools.workflow_lib as workflow_lib


def make_comment(body: str, created_at: str, updated_at: str | None = None) -> dict:
    return {
        "body": body,
        "created_at": created_at,
        "updated_at": updated_at or created_at,
    }


class WorkflowLabelTests(unittest.TestCase):
    def test_build_primary_label_set_replaces_existing_primary_label(self) -> None:
        labels = ["bug", "wf:intake", "docs"]

        updated = workflow_lib.build_primary_label_set(labels, "wf:codex-queued")

        self.assertEqual(
            updated,
            ["bug", "docs", "wf:codex-queued"],
        )

    def test_primary_labels_constant_contains_phase1_states(self) -> None:
        self.assertEqual(
            workflow_lib.PRIMARY_LABELS,
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

    def test_formal_marker_constants_are_stable(self) -> None:
        self.assertEqual(
            workflow_lib.MARKER_FORMAL_DIAGNOSE, "<!-- wf:formal-diagnose -->"
        )
        self.assertEqual(
            workflow_lib.MARKER_FORMAL_REVIEW_PLAN, "<!-- wf:formal-review-plan -->"
        )
        self.assertEqual(
            workflow_lib.MARKER_FORMAL_APPROVAL, "<!-- wf:formal-approval -->"
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

        latest = workflow_lib.find_latest_marker_comment(comments, "<!-- wf:plan -->")

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


class AnthropicWorkflowTests(unittest.TestCase):
    def test_normalize_anthropic_messages_url_appends_messages_endpoint(self) -> None:
        self.assertEqual(
            workflow_lib.normalize_anthropic_messages_url("https://kuaipao.ai"),
            "https://kuaipao.ai/v1/messages",
        )

    def test_normalize_anthropic_messages_url_replaces_trailing_v1_path(self) -> None:
        self.assertEqual(
            workflow_lib.normalize_anthropic_messages_url("https://kuaipao.ai/v1/"),
            "https://kuaipao.ai/v1/messages",
        )

    def test_extract_anthropic_text_joins_multiple_text_blocks(self) -> None:
        payload = {
            "content": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ]
        }

        self.assertEqual(workflow_lib.extract_anthropic_text(payload), "first\n\nsecond")

    def test_extract_anthropic_text_raises_when_no_text_blocks_exist(self) -> None:
        with self.assertRaises(workflow_lib.WorkflowError):
            workflow_lib.extract_anthropic_text({"content": [{"type": "tool_use"}]})

    @patch("tools.workflow_lib.requests.post")
    def test_call_openai_text_uses_anthropic_messages_endpoint(self, mock_post: Mock) -> None:
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "msg_123",
            "content": [{"type": "text", "text": "ok"}],
        }
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        config = workflow_lib.OpenAIConfig(
            openai_api_key="sk-test",
            openai_api_base="https://kuaipao.ai",
            openai_model="claude-opus-4-7",
            openai_endpoint_style="anthropic_messages",
            openai_reasoning_effort="medium",
            max_output_tokens=1800,
        )

        text, response_id = workflow_lib.call_openai_text(
            config, "system text", "user text"
        )

        self.assertEqual(text, "ok")
        self.assertEqual(response_id, "msg_123")
        mock_post.assert_called_once()
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://kuaipao.ai/v1/messages",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["system"],
            "system text",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["json"]["messages"],
            [{"role": "user", "content": "user text"}],
        )
        self.assertEqual(mock_post.call_args.kwargs["json"]["max_tokens"], 1800)
        self.assertEqual(
            mock_post.call_args.kwargs["headers"]["x-api-key"],
            "sk-test",
        )
        self.assertEqual(
            mock_post.call_args.kwargs["headers"]["anthropic-version"],
            "2023-06-01",
        )


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
