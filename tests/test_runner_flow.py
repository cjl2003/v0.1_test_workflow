import unittest

from tools.runner_pickup import (
    build_success_tag,
    parse_request_metadata,
    render_codex_run_comment,
    render_run_result_document,
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


if __name__ == "__main__":
    unittest.main()
