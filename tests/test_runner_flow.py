import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.backend_runner import BackendCandidate
from tools.runner_pickup import (
    build_candidate,
    build_success_tag,
    dispatch_candidate,
    parse_request_metadata,
    render_codex_run_comment,
    render_run_result_document,
    run_command,
    select_execution_mode,
)


REQUEST_DOC = """# Frontend Request: Test

- Request Id: `req-20260417-123456-test`
- Title: `Implement mode switch fix`
- Stage: `phase-1`
- Base Branch: `main`
- Work Branch: `request/2026-04-17-mode-switch-fix`
- Version: `r001`

## Goal
Implement the approved mode-switch frontend work.
"""


class RunnerFlowTests(unittest.TestCase):
    def test_parse_request_metadata_extracts_required_fields(self) -> None:
        metadata = parse_request_metadata(REQUEST_DOC)

        self.assertEqual(metadata["request_id"], "req-20260417-123456-test")
        self.assertEqual(metadata["base_branch"], "main")
        self.assertEqual(metadata["work_branch"], "request/2026-04-17-mode-switch-fix")
        self.assertEqual(metadata["version"], "r001")

    def test_select_execution_mode_prefers_rework_when_codex_fix_is_latest(self) -> None:
        mode = select_execution_mode(
            latest_plan_at="2026-04-17T00:05:00Z",
            latest_approve_plan_at="2026-04-17T00:06:00Z",
            latest_gpt_review_at="2026-04-17T00:10:00Z",
            latest_codex_fix_at="2026-04-17T00:11:00Z",
        )

        self.assertEqual(mode, "rework")

    def test_select_execution_mode_uses_plan_round_without_codex_fix(self) -> None:
        mode = select_execution_mode(
            latest_plan_at="2026-04-17T00:05:00Z",
            latest_approve_plan_at="2026-04-17T00:06:00Z",
            latest_gpt_review_at=None,
            latest_codex_fix_at=None,
        )

        self.assertEqual(mode, "plan")

    def test_build_success_tag_uses_phase1_format(self) -> None:
        tag = build_success_tag("20260417_153000", "r001")

        self.assertEqual(tag, "v0.1_frontend_pass_20260417_153000_r001")

    def test_render_run_result_document_keeps_commit_pending(self) -> None:
        document = render_run_result_document(
            request_id="req-20260417-123456-test",
            run_id="run-20260417-153000-r001",
            version="r001",
            tag="v0.1_frontend_pass_20260417_153000_r001",
            commands_executed=[
                "cmd /c codex exec --full-auto -C <worktree> -",
                "cmd /c sim/run_iverilog.bat",
                "python tools/check_golden.py",
            ],
            verification_summary=[
                "RTL compile succeeds.",
                "Simulation output includes Simulation Passed.",
                "Golden vector verification succeeds.",
            ],
            artifact_paths=[
                "docs/runs/req-20260417-123456-test/20260417_153000.md",
                "C:/Users/test/.codex-phase1-runner/logs/run-20260417-153000-r001/codex.log",
            ],
            notes="Successful phase-1 frontend run.",
        )

        self.assertIn("- Commit: `pending`", document)
        self.assertIn("Successful phase-1 frontend run.", document)

    def test_render_codex_run_comment_for_success(self) -> None:
        comment = render_codex_run_comment(
            status="success",
            run_id="run-20260417-153000-r001",
            verification_summary=[
                "sim/run_iverilog.bat: PASS",
                "python tools/check_golden.py: PASS",
            ],
            run_result_path="docs/runs/req-20260417-123456-test/20260417_153000.md",
            commit_id="abc123def456",
            tag="v0.1_frontend_pass_20260417_153000_r001",
            failure_step=None,
            notes="Ready for GPT frontend review.",
        )

        self.assertIn("<!-- wf:codex-run -->", comment)
        self.assertIn("- Commit: `abc123def456`", comment)
        self.assertIn("- Run Result Path: `docs/runs/req-20260417-123456-test/20260417_153000.md`", comment)

    def test_render_codex_run_comment_for_failure(self) -> None:
        comment = render_codex_run_comment(
            status="failed",
            run_id="run-20260417-153000-r001",
            verification_summary=["cmd /c sim/run_iverilog.bat: FAIL"],
            run_result_path=None,
            commit_id=None,
            tag=None,
            failure_step="verification",
            notes="Verification failed before repository artifacts were written.",
        )

        self.assertIn("- Failure Step: `verification`", comment)
        self.assertNotIn("Run Result Path", comment)

    def test_run_command_uses_utf8_for_stdin_text(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(*args, **kwargs):
            captured.update(kwargs)
            return mock.Mock(returncode=0, stdout="ok", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "stdout.log"
            stderr_path = Path(tmpdir) / "stderr.log"

            with mock.patch("tools.runner_pickup.subprocess.run", side_effect=fake_run):
                result = run_command(
                    ["cmd", "/c", "echo", "ok"],
                    cwd=Path(tmpdir),
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    input_text="中文 prompt",
                )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured["input"], "中文 prompt")
        self.assertEqual(captured["encoding"], "utf-8")
        self.assertTrue(captured["text"])

    def test_build_candidate_uses_backend_builder_when_state_is_backend_queued(self) -> None:
        client = mock.Mock()
        client.config.github_repo = "owner/repo"
        pr = {
            "number": 15,
            "labels": [{"name": "wf:backend-queued"}],
            "head": {
                "ref": "request/2026-04-17-phase2a-smoke",
                "repo": {"full_name": "owner/repo"},
            },
        }
        sentinel = BackendCandidate(
            pr_number=15,
            queue_time="2026-04-17T10:00:00Z",
            request_path="docs/requests/2026-04-17-phase2a-smoke.md",
            head_branch="request/2026-04-17-phase2a-smoke",
        )

        with mock.patch("tools.runner_pickup.build_backend_candidate", return_value=sentinel) as patched:
            candidate = build_candidate(client, pr)

        self.assertIs(candidate, sentinel)
        patched.assert_called_once_with(client, pr)

    def test_dispatch_candidate_routes_backend_candidate(self) -> None:
        client = mock.Mock()
        candidate = BackendCandidate(
            pr_number=15,
            queue_time="2026-04-17T10:00:00Z",
            request_path="docs/requests/2026-04-17-phase2a-smoke.md",
            head_branch="request/2026-04-17-phase2a-smoke",
        )

        with mock.patch("tools.runner_pickup.execute_backend_candidate") as backend_exec:
            with mock.patch("tools.runner_pickup.execute_candidate") as frontend_exec:
                dispatch_candidate(client, candidate)

        backend_exec.assert_called_once_with(client, candidate)
        frontend_exec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
