import io
import sys
import unittest
from unittest import mock

from tools.formal_subloop import (
    approve_latest_formal_plan,
    extract_latest_formal_review_plan,
    main,
    post_formal_diagnose,
)
from tools.workflow_lib import WorkflowError


def make_comment(body: str, created_at: str, updated_at: str | None = None) -> dict:
    return {
        "body": body,
        "created_at": created_at,
        "updated_at": updated_at or created_at,
    }


class FormalSubloopTests(unittest.TestCase):
    def test_extract_latest_formal_review_plan_returns_latest_marker_body(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            make_comment(
                "<!-- wf:formal-review-plan -->\nold plan",
                "2026-04-18T10:00:00Z",
                "2026-04-18T10:01:00Z",
            ),
            make_comment(
                "<!-- wf:formal-review-plan -->\nlatest plan",
                "2026-04-18T10:02:00Z",
                "2026-04-18T10:05:00Z",
            ),
            make_comment(
                "<!-- wf:formal-diagnose -->\nnoise",
                "2026-04-18T10:06:00Z",
            ),
        ]

        body = extract_latest_formal_review_plan(client, 20)

        self.assertEqual(body, "<!-- wf:formal-review-plan -->\nlatest plan")
        client.list_issue_comments.assert_called_once_with(20)

    def test_extract_latest_formal_review_plan_requires_marker(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            make_comment("<!-- wf:formal-diagnose -->\nbody", "2026-04-18T10:00:00Z"),
        ]

        with self.assertRaisesRegex(WorkflowError, "wf:formal-review-plan"):
            extract_latest_formal_review_plan(client, 20)

    def test_post_formal_diagnose_requires_marker_and_creates_new_comment(self) -> None:
        client = mock.Mock()
        body = "<!-- wf:formal-diagnose -->\n## Phase-2A Formal Diagnose"

        post_formal_diagnose(client, 20, body)

        client.create_marker_comment.assert_called_once_with(
            20,
            "<!-- wf:formal-diagnose -->",
            body,
        )

    def test_post_formal_diagnose_rejects_body_without_marker(self) -> None:
        client = mock.Mock()

        with self.assertRaisesRegex(WorkflowError, "wf:formal-diagnose"):
            post_formal_diagnose(client, 20, "## Phase-2A Formal Diagnose")

        client.create_marker_comment.assert_not_called()

    def test_approve_latest_formal_plan_uses_latest_review_plan_title(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            make_comment(
                "<!-- wf:formal-review-plan -->\n- Decision: `reject`\n### Next Plan\n- Plan Title: Old plan",
                "2026-04-18T10:00:00Z",
                "2026-04-18T10:01:00Z",
            ),
            make_comment(
                "<!-- wf:formal-review-plan -->\n- Decision: `approve`\n### Next Plan\n- Plan Title: Narrow proof to one compare point",
                "2026-04-18T10:02:00Z",
                "2026-04-18T10:05:00Z",
            ),
        ]
        client.list_issue_comments.return_value[0]["id"] = 101
        client.list_issue_comments.return_value[0]["html_url"] = "https://example.invalid/comment/101"
        client.list_issue_comments.return_value[1]["id"] = 202
        client.list_issue_comments.return_value[1]["html_url"] = "https://example.invalid/comment/202"

        approve_latest_formal_plan(client, 20)

        client.create_marker_comment.assert_called_once()
        args = client.create_marker_comment.call_args.args
        self.assertEqual(args[0], 20)
        self.assertEqual(args[1], "<!-- wf:formal-approval -->")
        self.assertIn("Narrow proof to one compare point", args[2])
        self.assertIn("Approved Review-Plan Comment ID", args[2])
        self.assertIn("202", args[2])
        self.assertIn("Approved Review-Plan Comment URL", args[2])
        self.assertIn("https://example.invalid/comment/202", args[2])
        self.assertIn("<!-- wf:formal-approval -->", args[2])

    def test_approve_latest_formal_plan_requires_latest_review_plan(self) -> None:
        client = mock.Mock()
        client.list_issue_comments.return_value = []

        with self.assertRaisesRegex(WorkflowError, "wf:formal-review-plan"):
            approve_latest_formal_plan(client, 20)

    @mock.patch("tools.formal_subloop.GitHubClient")
    @mock.patch("tools.formal_subloop.load_github_config")
    @mock.patch("tools.formal_subloop.parse_args")
    def test_main_show_latest_plan_prints_latest_body(
        self,
        parse_args: mock.Mock,
        load_github_config: mock.Mock,
        github_client: mock.Mock,
    ) -> None:
        parse_args.return_value = mock.Mock(command="show-latest-plan", pr_number=20)
        load_github_config.return_value = mock.Mock()
        client = mock.Mock()
        client.list_issue_comments.return_value = [
            make_comment(
                "<!-- wf:formal-review-plan -->\nlatest plan body",
                "2026-04-18T10:02:00Z",
                "2026-04-18T10:05:00Z",
            )
        ]
        github_client.return_value = client
        stdout = io.StringIO()

        with mock.patch.object(sys, "stdout", stdout):
            exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "<!-- wf:formal-review-plan -->\nlatest plan body")


if __name__ == "__main__":
    unittest.main()
