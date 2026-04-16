import argparse
import os
import unittest
from unittest import mock

from tools.reviewer import (
    DEFAULT_MAX_DIFF_CHARS,
    Config,
    format_failure_comment_body,
    get_env,
    load_config,
)


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

    def test_failure_comment_body_contains_status_and_reason(self) -> None:
        config = Config(
            openai_api_key="sk-test",
            github_token="ghs-test",
            github_repo="owner/repo",
            pr_number=2,
            openai_model="gpt-5.4",
            openai_reasoning_effort="medium",
            max_diff_chars=120000,
            max_output_tokens=1800,
            github_api_base="https://api.github.com",
            github_api_version="2022-11-28",
            openai_api_base="https://api.openai.com/v1",
            dry_run=False,
        )

        body = format_failure_comment_body(
            config, "Calling OpenAI Responses API failed with HTTP 429"
        )

        self.assertIn("Status: `failed`", body)
        self.assertIn("HTTP 429", body)


if __name__ == "__main__":
    unittest.main()
