import unittest

from tools.formal_protocol import (
    render_formal_approval_comment,
    render_formal_diagnose_comment,
    render_formal_review_plan_comment,
)


class FormalProtocolRenderTests(unittest.TestCase):
    def test_render_formal_diagnose_comment_includes_expected_sections(self) -> None:
        rendered = render_formal_diagnose_comment(
            context="Latest synth run hit an unresolved timing failure.",
            current_stop_point="The run stopped after the first failing report.",
            what_was_tried=["Re-ran the same command.", "Checked the timing report."],
            strongest_evidence=["`reports/timing.rpt` shows hold violations."],
            key_logs_or_paths=["`logs/synth.log`", "`reports/timing.rpt`"],
            ruled_out=["A missing input file."],
            candidate_next_step="Inspect the failing path in the timing report.",
            questions_for_gpt=["What is the most likely root cause?"],
        )

        self.assertIn("<!-- wf:formal-diagnose -->", rendered)
        self.assertIn("### Context", rendered)
        self.assertIn("### Current Stop Point", rendered)
        self.assertIn("### What Was Tried", rendered)
        self.assertIn("### Strongest Evidence", rendered)
        self.assertIn("### Key Logs / Paths", rendered)
        self.assertIn("### Ruled Out", rendered)
        self.assertIn("### Candidate Next Step", rendered)
        self.assertIn("### Questions For GPT", rendered)

    def test_render_formal_review_plan_comment_includes_decision_metadata(self) -> None:
        rendered = render_formal_review_plan_comment(
            reason="The latest evidence is sufficient to propose the next formal step.",
            next_plan="Run the failing formal check with targeted assertions.",
            success_criteria="The failure is reproduced with a minimal trace.",
            do_not_do=["Do not change implementation code yet."],
        )

        self.assertIn("<!-- wf:formal-review-plan -->", rendered)
        self.assertIn("- Decision: `formal-review-plan`", rendered)
        self.assertIn("### Reason", rendered)
        self.assertIn("### Next Plan", rendered)
        self.assertIn("### Success Criteria", rendered)
        self.assertIn("### Do Not Do", rendered)

    def test_render_formal_approval_comment_mentions_plan_title_and_relay(self) -> None:
        rendered = render_formal_approval_comment("Patch the failing timing arc only")

        self.assertIn("<!-- wf:formal-approval -->", rendered)
        self.assertIn("latest wf:formal-review-plan", rendered)
        self.assertIn("desktop user via Codex relay", rendered)
        self.assertIn("Patch the failing timing arc only", rendered)


if __name__ == "__main__":
    unittest.main()
