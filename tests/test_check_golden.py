import unittest
from pathlib import Path

from tools.check_golden import parse_golden_vectors, verify_golden_vectors


class CheckGoldenTests(unittest.TestCase):
    def test_parse_golden_vectors_reads_expected_sections(self) -> None:
        parsed = parse_golden_vectors(Path("docs/golden_vectors.md").read_text(encoding="utf-8"))

        self.assertEqual(parsed["products"], [12, 240, 994, 96048, 1780992, 15068144])
        self.assertEqual(parsed["mode0_sum_out"][-1], 71920)
        self.assertEqual(parsed["switch_sum_out"][-1], 167968)

    def test_verify_golden_vectors_rejects_mismatched_document(self) -> None:
        tampered = (
            Path("docs/golden_vectors.md")
            .read_text(encoding="utf-8")
            .replace("71920", "71921", 1)
        )

        ok, messages = verify_golden_vectors(tampered)

        self.assertFalse(ok)
        self.assertTrue(any("mode 0 sum_out" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
