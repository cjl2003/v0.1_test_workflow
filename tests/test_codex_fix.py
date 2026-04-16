import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.codex_fix import (
    FIX_TRIGGER,
    apply_model_edits,
    extract_json_payload,
    load_config,
    normalize_fix_payload,
    parse_fix_command,
    resolve_repo_path,
)


class CodexFixTests(unittest.TestCase):
    def test_parse_fix_command_extracts_user_note(self) -> None:
        note = parse_fix_command("/codex-fix Please prioritize the RTL blocker.")
        self.assertEqual(note, "Please prioritize the RTL blocker.")

    def test_extract_json_payload_accepts_fenced_json(self) -> None:
        payload = extract_json_payload(
            """```json
            {"summary": "done", "rationale": [], "edits": []}
            ```"""
        )
        self.assertEqual(payload["summary"], "done")

    def test_normalize_fix_payload_rejects_disallowed_paths(self) -> None:
        with self.assertRaisesRegex(Exception, "disallowed file"):
            normalize_fix_payload(
                {
                    "summary": "bad",
                    "rationale": [],
                    "edits": [{"path": "other.v", "content": "module x; endmodule"}],
                },
                {"rtl/top.v"},
            )

    def test_apply_model_edits_writes_full_file_replacements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            file_path = repo_root / "rtl" / "demo.v"
            file_path.parent.mkdir(parents=True)
            file_path.write_text("module demo;\nendmodule\n", encoding="utf-8")

            changed = apply_model_edits(
                repo_root,
                [{"path": "rtl/demo.v", "content": "module demo;\n  wire x;\nendmodule\n"}],
            )

            self.assertEqual(changed, ["rtl/demo.v"])
            self.assertIn("wire x;", file_path.read_text(encoding="utf-8"))

    def test_resolve_repo_path_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(Exception, "escapes repository root"):
                resolve_repo_path(Path(temp_dir), "..\\outside.txt")

    def test_load_config_uses_fix_model_override(self) -> None:
        env = {
            "OPENAI_API_KEY": "sk-test",
            "GITHUB_TOKEN": "ghs-test",
            "GITHUB_REPO": "owner/repo",
            "PR_NUMBER": "2",
            "COMMENT_BODY": FIX_TRIGGER,
            "OPENAI_MODEL": "review-model",
            "OPENAI_FIX_MODEL": "fix-model",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            config = load_config(argparse.Namespace(pr_number=None, dry_run=False))

        self.assertEqual(config.openai_model, "fix-model")


if __name__ == "__main__":
    unittest.main()
