import unittest

from tools.formal_protocol import (
    render_formal_approval_comment,
    render_formal_diagnose_comment,
    render_formal_review_plan_comment,
)
from tools.workflow_lib import WorkflowError


class FormalProtocolRenderTests(unittest.TestCase):
    def test_render_formal_diagnose_comment_uses_expected_contract(self) -> None:
        rendered = render_formal_diagnose_comment(
            pr_number=20,
            backend_run_id="phase2a-20260418_104642-r001",
            commit_ref="0a5836659d7f8c647862b9eb7f87eb5c0e4cb40d",
            formal_status="undet",
            affected_compare_points=["miter_mode0_prev_product_28__IQ"],
            current_stop_point="Single compare point remains undetermined after targeted runs.",
            attempts=[
                ("target4 prove", "3 pass, 1 undet"),
                ("single-point long run", "still undet after ~1190s"),
            ],
            strongest_evidence=[
                "PO-only prove shows top-level outputs trivially true.",
                "No output-related fail observed in observable cluster run.",
            ],
            evidence_paths=[
                "work_pre_target4/pre_target4.out.log.log",
                "work_pre_mode0p28_long/pre_mode0p28_long.out.log.log",
            ],
            ruled_out=["Missing reset definition is no longer the main blocker."],
            candidate_next_steps=[
                "Strengthen proof around mode0_prev_product_28 only.",
                "Add one tighter observability experiment tied to mode0 output path.",
            ],
            current_leaning="Strengthen the single compare-point proof first.",
        )

        self.assertIn("<!-- wf:formal-diagnose -->", rendered)
        self.assertIn("### Context", rendered)
        self.assertIn("PR: `20`", rendered)
        self.assertIn("Backend Run ID: `phase2a-20260418_104642-r001`", rendered)
        self.assertIn("Commit / Ref: `0a5836659d7f8c647862b9eb7f87eb5c0e4cb40d`", rendered)
        self.assertIn("Formal Status: `undet`", rendered)
        self.assertIn("miter_mode0_prev_product_28__IQ", rendered)
        self.assertIn("### Current Stop Point", rendered)
        self.assertIn("### What Was Tried", rendered)
        self.assertIn("target4 prove: 3 pass, 1 undet", rendered)
        self.assertIn("single-point long run: still undet after ~1190s", rendered)
        self.assertIn("### Strongest Evidence", rendered)
        self.assertIn("### Key Logs / Paths", rendered)
        self.assertIn("### Ruled Out", rendered)
        self.assertIn("### Candidate Next Step", rendered)
        self.assertIn("Current Leaning: Strengthen the single compare-point proof first.", rendered)
        self.assertIn("### Questions For GPT", rendered)

    def test_render_formal_diagnose_comment_cleans_blank_items(self) -> None:
        rendered = render_formal_diagnose_comment(
            pr_number=20,
            backend_run_id="phase2a-20260418_104642-r001",
            commit_ref="0a5836659d7f8c647862b9eb7f87eb5c0e4cb40d",
            formal_status="undet",
            affected_compare_points=["  ", "miter_mode0_prev_product_28__IQ", ""],
            current_stop_point="Single compare point remains undetermined after targeted runs.",
            attempts=[
                ("target4 prove", "3 pass, 1 undet"),
                ("   ", "ignored"),
                ("single-point long run", "still undet after ~1190s"),
                ("", "ignored too"),
            ],
            strongest_evidence=[
                "PO-only prove shows top-level outputs trivially true.",
            ],
            evidence_paths=["", "  ", "work_pre_mode0p28_long/pre_mode0p28_long.out.log.log"],
            ruled_out=["Missing reset definition is no longer the main blocker."],
            candidate_next_steps=["Strengthen proof around mode0_prev_product_28 only."],
            current_leaning="Strengthen the single compare-point proof first.",
        )

        self.assertIn("miter_mode0_prev_product_28__IQ", rendered)
        self.assertIn("target4 prove: 3 pass, 1 undet", rendered)
        self.assertIn("single-point long run: still undet after ~1190s", rendered)
        self.assertIn("work_pre_mode0p28_long/pre_mode0p28_long.out.log.log", rendered)
        self.assertNotIn("ignored too", rendered)
        self.assertNotIn("- ``", rendered)
        self.assertNotIn("- `  `", rendered)
        self.assertNotIn("-    : ignored", rendered)

    def test_render_formal_diagnose_comment_handles_none_items_and_current_leaning(self) -> None:
        rendered = render_formal_diagnose_comment(
            pr_number=20,
            backend_run_id="phase2a-20260418_104642-r001",
            commit_ref="0a5836659d7f8c647862b9eb7f87eb5c0e4cb40d",
            formal_status="undet",
            affected_compare_points=[None, "miter_mode0_prev_product_28__IQ"],
            current_stop_point="Single compare point remains undetermined after targeted runs.",
            attempts=[(None, "ignored"), ("target4 prove", None), ("valid", "kept")],
            strongest_evidence=["PO-only prove shows top-level outputs trivially true."],
            evidence_paths=[None, "work_pre_mode0p28_long/pre_mode0p28_long.out.log.log"],
            ruled_out=["Missing reset definition is no longer the main blocker."],
            candidate_next_steps=["Strengthen proof around mode0_prev_product_28 only."],
            current_leaning=None,
        )

        self.assertIn("miter_mode0_prev_product_28__IQ", rendered)
        self.assertIn("work_pre_mode0p28_long/pre_mode0p28_long.out.log.log", rendered)
        self.assertIn("valid: kept", rendered)
        self.assertNotIn("ignored", rendered)
        self.assertNotIn("None", rendered)

    def test_render_formal_diagnose_comment_rejects_blank_required_scalars(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "backend_run_id"):
            render_formal_diagnose_comment(
                pr_number=20,
                backend_run_id="  ",
                commit_ref="0a5836659d7f8c647862b9eb7f87eb5c0e4cb40d",
                formal_status="undet",
                affected_compare_points=["miter_mode0_prev_product_28__IQ"],
                current_stop_point="Single compare point remains undetermined after targeted runs.",
                attempts=[("target4 prove", "3 pass, 1 undet")],
                strongest_evidence=["PO-only prove shows top-level outputs trivially true."],
                evidence_paths=["work_pre_mode0p28_long/pre_mode0p28_long.out.log.log"],
                ruled_out=["Missing reset definition is no longer the main blocker."],
                candidate_next_steps=["Strengthen proof around mode0_prev_product_28 only."],
                current_leaning="Strengthen the single compare-point proof first.",
            )

    def test_render_formal_diagnose_comment_rejects_none_required_scalar(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "backend_run_id"):
            render_formal_diagnose_comment(
                pr_number=20,
                backend_run_id=None,
                commit_ref="0a5836659d7f8c647862b9eb7f87eb5c0e4cb40d",
                formal_status="undet",
                affected_compare_points=["miter_mode0_prev_product_28__IQ"],
                current_stop_point="Single compare point remains undetermined after targeted runs.",
                attempts=[("target4 prove", "3 pass, 1 undet")],
                strongest_evidence=["PO-only prove shows top-level outputs trivially true."],
                evidence_paths=["work_pre_mode0p28_long/pre_mode0p28_long.out.log.log"],
                ruled_out=["Missing reset definition is no longer the main blocker."],
                candidate_next_steps=["Strengthen proof around mode0_prev_product_28 only."],
                current_leaning="Strengthen the single compare-point proof first.",
            )

    def test_render_formal_review_plan_comment_uses_actual_decision(self) -> None:
        rendered = render_formal_review_plan_comment(
            decision="revise",
            reasons=["Current diagnosis is directionally right but still too broad."],
            plan_title="Narrow proof to one compare point",
            hypothesis="The blocker is isolated to a single internal state point.",
            one_experiment="Run one focused proof or observability experiment for that point only.",
            expected_evidence="Either the point proves or a concrete counterexample appears.",
            stop_condition="Stop after one targeted experiment.",
            success_criteria="A narrower conclusion replaces the current broad undet cluster claim.",
            do_not_do=["Do not expand back into broad cluster proves."],
        )

        self.assertIn("<!-- wf:formal-review-plan -->", rendered)
        self.assertIn("- Decision: `revise`", rendered)
        self.assertIn("### Reason", rendered)
        self.assertIn("Current diagnosis is directionally right but still too broad.", rendered)
        self.assertIn("### Next Plan", rendered)
        self.assertIn("Plan Title: Narrow proof to one compare point", rendered)
        self.assertIn("Hypothesis: The blocker is isolated to a single internal state point.", rendered)
        self.assertIn(
            "One Experiment / One Fix Direction: Run one focused proof or observability experiment for that point only.",
            rendered,
        )
        self.assertIn(
            "Expected Evidence: Either the point proves or a concrete counterexample appears.",
            rendered,
        )
        self.assertIn("Stop Condition: Stop after one targeted experiment.", rendered)
        self.assertIn("### Success Criteria", rendered)
        self.assertIn("### Do Not Do", rendered)

    def test_render_formal_review_plan_comment_rejects_invalid_decision(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "decision"):
            render_formal_review_plan_comment(
                decision=" maybe ",
                reasons=["Current diagnosis is directionally right but still too broad."],
                plan_title="Narrow proof to one compare point",
                hypothesis="The blocker is isolated to a single internal state point.",
                one_experiment="Run one focused proof or observability experiment for that point only.",
                expected_evidence="Either the point proves or a concrete counterexample appears.",
                stop_condition="Stop after one targeted experiment.",
                success_criteria="A narrower conclusion replaces the current broad undet cluster claim.",
                do_not_do=["Do not expand back into broad cluster proves."],
            )

    def test_render_formal_review_plan_comment_rejects_missing_required_field(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "plan_title"):
            render_formal_review_plan_comment(
                decision="revise",
                reasons=["Current diagnosis is directionally right but still too broad."],
                plan_title="   ",
                hypothesis="The blocker is isolated to a single internal state point.",
                one_experiment="Run one focused proof or observability experiment for that point only.",
                expected_evidence="Either the point proves or a concrete counterexample appears.",
                stop_condition="Stop after one targeted experiment.",
                success_criteria="A narrower conclusion replaces the current broad undet cluster claim.",
                do_not_do=["Do not expand back into broad cluster proves."],
            )

    def test_render_formal_approval_comment_mentions_plan_title_and_relay(self) -> None:
        rendered = render_formal_approval_comment("Narrow proof to one compare point")

        self.assertIn("<!-- wf:formal-approval -->", rendered)
        self.assertIn("latest wf:formal-review-plan", rendered)
        self.assertIn("desktop user via Codex relay", rendered)
        self.assertIn("Narrow proof to one compare point", rendered)

    def test_render_formal_approval_comment_rejects_blank_plan_title(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "plan_title"):
            render_formal_approval_comment("   ")

    def test_render_formal_approval_comment_rejects_none_plan_title(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "plan_title"):
            render_formal_approval_comment(None)


if __name__ == "__main__":
    unittest.main()
