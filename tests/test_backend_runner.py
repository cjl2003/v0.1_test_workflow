import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.backend_runner import (
    BackendCandidate,
    build_backend_candidate,
    execute_backend_candidate,
    validate_phase2a_outputs,
)


class BackendRunnerTests(unittest.TestCase):
    def test_backend_runner_marks_blocked_when_ssh_file_is_missing(self) -> None:
        client = mock.Mock()
        candidate = BackendCandidate(
            pr_number=15,
            queue_time="2026-04-17T10:00:00Z",
            request_path="docs/requests/2026-04-17-phase2a-smoke.md",
            head_branch="request/2026-04-17-phase2a-smoke",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch(
                "tools.backend_runner.SSH_INFO_PATH",
                Path(tmpdir) / "missing.txt",
            ):
                execute_backend_candidate(client, candidate)

        client.set_primary_state.assert_called_with(15, "wf:backend-blocked")
        client.upsert_marker_comment.assert_called_once()
        comment_body = client.upsert_marker_comment.call_args.args[2]
        self.assertIn("Waiting for refreshed SSH info.", comment_body)

    def test_backend_runner_requires_phase2a_baseline_outputs(self) -> None:
        missing = validate_phase2a_outputs(
            local_dir=Path("C:/missing/local"),
            repo_dir=Path("docs/runs/req-test/backend/phase2a-1"),
        )

        self.assertIn("mapped.v", missing)
        self.assertIn("reports/formal_ec_summary.md", missing)

    def test_build_backend_candidate_uses_latest_continue_backend_comment(self) -> None:
        client = mock.Mock()
        client.config.github_repo = "owner/repo"
        client.list_pull_request_files.return_value = [
            {"filename": "docs/requests/2026-04-17-phase2a-smoke.md"},
        ]
        client.list_issue_comments.return_value = [
            {
                "body": "/continue-backend",
                "created_at": "2026-04-17T10:00:00Z",
                "updated_at": "2026-04-17T10:00:00Z",
            }
        ]
        pr = {
            "number": 15,
            "labels": [{"name": "wf:backend-queued"}],
            "head": {
                "ref": "request/2026-04-17-phase2a-smoke",
                "repo": {"full_name": "owner/repo"},
            },
        }

        candidate = build_backend_candidate(client, pr)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.pr_number, 15)
        self.assertEqual(candidate.request_path, "docs/requests/2026-04-17-phase2a-smoke.md")
        self.assertEqual(candidate.queue_kind, "backend")


if __name__ == "__main__":
    unittest.main()
