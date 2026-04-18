import unittest

from tools.backend_review import normalize_backend_review_payload


class BackendReviewTests(unittest.TestCase):
    def test_normalize_backend_review_payload_for_pass(self) -> None:
        rendered = normalize_backend_review_payload(
            {
                "outcome": "pass",
                "summary": "Synthesis, mapped netlist generation, constraint loading, and Formal EC all pass.",
                "hard_findings": [],
                "baseline_warnings": ["Synthesis timing is still far from the 1GHz target."],
                "next_gate_recommendation": "ready-for-phase-2b",
            }
        )

        self.assertEqual(rendered.target_state, "wf:backend-passed")
        self.assertIn("Outcome: `pass`", rendered.body)
        self.assertIn("ready-for-phase-2b", rendered.body)

    def test_normalize_backend_review_payload_for_failed(self) -> None:
        rendered = normalize_backend_review_payload(
            {
                "outcome": "failed",
                "summary": "Formal EC did not pass.",
                "hard_findings": ["Formal EC summary shows a failing equivalence result."],
                "baseline_warnings": [],
                "next_gate_recommendation": "revise-rtl-before-phase-2b",
            }
        )

        self.assertEqual(rendered.target_state, "wf:backend-failed")
        self.assertIn("Outcome: `failed`", rendered.body)
        self.assertIn("Formal EC summary shows a failing equivalence result.", rendered.body)


if __name__ == "__main__":
    unittest.main()
