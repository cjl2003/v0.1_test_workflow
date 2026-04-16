import argparse
import os
import unittest
from unittest import mock

from tools.reviewer import DEFAULT_MAX_DIFF_CHARS, get_env, load_config


class ReviewerEnvTests(unittest.TestCase):
    def test_get_env_uses_default_when_variable_is_blank(self) -> None:
        with mock.patch.dict(os.environ, {"MAX_DIFF_CHARS": "   "}, clear=False):
            self.assertEqual(get_env("MAX_DIFF_CHARS", "120000"), "120000")

    def test_load_config_falls_back_when_optional_action_vars_are_blank(self) -> None:
        env = {
            "OPENAI_API_KEY": "sk-test",
            "GITHUB_TOKEN": "ghs-test",
            "GITHUB_REPO": "owner/repo",
            "PR_NUMBER": "2",
            "MAX_DIFF_CHARS": "",
            "OPENAI_MAX_OUTPUT_TOKENS": "",
            "OPENAI_REASONING_EFFORT": "",
            "OPENAI_MODEL": "",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config(argparse.Namespace(pr_number=None, dry_run=False))

        self.assertEqual(config.max_diff_chars, DEFAULT_MAX_DIFF_CHARS)
        self.assertEqual(config.openai_model, "gpt-5.4")
        self.assertEqual(config.openai_reasoning_effort, "medium")


if __name__ == "__main__":
    unittest.main()
