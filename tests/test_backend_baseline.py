import unittest
from pathlib import Path

from tools.backend_baseline import (
    build_phase2a_local_dir,
    build_phase2a_repo_dir,
    build_phase2a_run_id,
    build_phase2a_tag,
    render_phase2a_review_comment,
    render_phase2a_run_comment,
    render_phase2a_summary_document,
)


class Phase2ABaselineTests(unittest.TestCase):
    def test_build_phase2a_run_id_uses_stable_format(self) -> None:
        run_id = build_phase2a_run_id("20260417_230500", "r003")

        self.assertEqual(run_id, "phase2a-20260417_230500-r003")

    def test_build_phase2a_tag_uses_ascii_format(self) -> None:
        tag = build_phase2a_tag("pass", "20260417_230500", "r003")

        self.assertEqual(tag, "v0.1_phase2a_pass_20260417_230500_r003")

    def test_build_phase2a_repo_dir_is_request_scoped(self) -> None:
        path = build_phase2a_repo_dir("req-1", "phase2a-20260417_230500-r003")

        self.assertEqual(
            path.as_posix(),
            "docs/runs/req-1/backend/phase2a-20260417_230500-r003",
        )

    def test_build_phase2a_local_dir_is_request_scoped(self) -> None:
        path = build_phase2a_local_dir("req-1", "phase2a-20260417_230500-r003")

        self.assertEqual(
            path,
            Path.home() / ".codex" / "backend_runs" / "req-1" / "phase2a-20260417_230500-r003",
        )

    def test_render_phase2a_summary_document_mentions_synthesis_and_formal_ec(self) -> None:
        document = render_phase2a_summary_document(
            request_id="req-1",
            run_id="phase2a-20260417_230500-r003",
            version="r003",
            tag="v0.1_phase2a_pass_20260417_230500_r003",
            synthesis_status="pass",
            mapped_netlist_status="present",
            constraints_status="loaded",
            formal_ec_status="pass",
            baseline_metrics={
                "power": "240uW",
                "area": "8123um2",
                "timing": "worst setup slack = -0.08ns",
            },
            notes="Phase-2A baseline run completed.",
        )

        self.assertIn("Formal EC", document)
        self.assertIn("240uW", document)
        self.assertIn("phase2a-20260417_230500-r003", document)

    def test_render_phase2a_run_comment_includes_status_headline(self) -> None:
        comment = render_phase2a_run_comment(
            status="success",
            run_id="phase2a-20260417_230500-r003",
            commit_id="abc123",
            tag="v0.1_phase2a_pass_20260417_230500_r003",
            local_package_dir="C:/Users/lalala/.codex/backend_runs/req-1/phase2a-20260417_230500-r003",
            repo_artifact_dir="docs/runs/req-1/backend/phase2a-20260417_230500-r003",
            synthesis_status="pass",
            mapped_netlist_status="present",
            constraints_status="loaded",
            formal_ec_status="pass",
            baseline_metrics={
                "power": "240uW",
                "area": "8123um2",
                "timing": "worst setup slack = -0.08ns",
            },
            notes="Ready for backend review.",
        )

        self.assertIn("Phase-2A Backend Run", comment)
        self.assertIn("Status: `success`", comment)
        self.assertIn("Formal EC", comment)
        self.assertIn("240uW", comment)

    def test_render_phase2a_review_comment_keeps_pass_fail_shape(self) -> None:
        comment = render_phase2a_review_comment(
            outcome="pass",
            summary="Synthesis, mapped netlist generation, constraint loading, and Formal EC all pass.",
            hard_findings=[],
            baseline_warnings=["Timing is still far from the 1GHz target."],
            next_gate_recommendation="ready-for-phase-2b",
        )

        self.assertIn("Phase-2A Backend Review", comment)
        self.assertIn("Outcome: `pass`", comment)
        self.assertIn("ready-for-phase-2b", comment)


if __name__ == "__main__":
    unittest.main()
