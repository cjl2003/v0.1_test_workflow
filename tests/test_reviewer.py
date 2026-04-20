import argparse
import os
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

from tools import workflow_lib
from tools.reviewer import (
    DEFAULT_MAX_DIFF_CHARS,
    Config,
    ReviewerError,
    call_openai_review,
    format_failure_comment_body,
    get_env,
    load_config,
)
from tools.workflow_lib import extract_chat_completions_text, should_fallback_to_chat_completions


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

    def test_load_config_prefers_review_model_override(self) -> None:
        env = {
            "OPENAI_API_KEY": "sk-test",
            "GITHUB_TOKEN": "ghs-test",
            "GITHUB_REPO": "owner/repo",
            "PR_NUMBER": "2",
            "OPENAI_MODEL": "fallback-model",
            "OPENAI_REVIEW_MODEL": "gpt-5.4",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config(argparse.Namespace(pr_number=None, dry_run=False))

        self.assertEqual(config.openai_model, "gpt-5.4")

    def test_failure_comment_body_contains_status_and_reason(self) -> None:
        config = Config(
            openai_api_key="sk-test",
            github_token="ghs-test",
            github_repo="owner/repo",
            pr_number=2,
            openai_model="gpt-5.4",
            openai_reasoning_effort="medium",
            openai_endpoint_style="auto",
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

    def test_extract_chat_completions_text_from_string_content(self) -> None:
        payload = {
            "choices": [
                {"message": {"content": "## Summary\n- found one issue"}}
            ]
        }
        self.assertEqual(
            extract_chat_completions_text(payload), "## Summary\n- found one issue"
        )

    def test_should_fallback_for_missing_responses_endpoint(self) -> None:
        self.assertTrue(
            should_fallback_to_chat_completions(
                "Calling OpenAI Responses API failed with HTTP 404: not found"
            )
        )

    def test_should_fallback_for_not_implemented_gateway_response(self) -> None:
        self.assertTrue(
            should_fallback_to_chat_completions(
                "Calling OpenAI Responses API failed with HTTP 500: "
                '{"error":{"message":"not implemented","code":"convert_request_failed"}}'
            )
        )


class ReviewerSharedClientTests(unittest.TestCase):
    @mock.patch("tools.reviewer.shared_call_openai_text")
    def test_call_openai_review_delegates_to_shared_client(self, mock_call: mock.Mock) -> None:
        mock_call.return_value = ("review body", "msg_456")
        config = Config(
            openai_api_key="sk-test",
            github_token="ghs-test",
            github_repo="owner/repo",
            pr_number=2,
            openai_model="claude-opus-4-7",
            openai_reasoning_effort="medium",
            openai_endpoint_style="anthropic_messages",
            max_diff_chars=120000,
            max_output_tokens=1800,
            github_api_base="https://api.github.com",
            github_api_version="2022-11-28",
            openai_api_base="https://kuaipao.ai",
            dry_run=False,
        )

        review_text, response_id = call_openai_review(config, "rules", "diff")

        self.assertEqual((review_text, response_id), ("review body", "msg_456"))
        shared_config = mock_call.call_args.args[0]
        self.assertEqual(shared_config.openai_endpoint_style, "anthropic_messages")
        self.assertEqual(shared_config.openai_api_base, "https://kuaipao.ai")

    @mock.patch("tools.reviewer.shared_call_openai_text")
    def test_call_openai_review_wraps_workflow_errors(self, mock_call: mock.Mock) -> None:
        mock_call.side_effect = workflow_lib.WorkflowError("shared failure")
        config = Config(
            openai_api_key="sk-test",
            github_token="ghs-test",
            github_repo="owner/repo",
            pr_number=2,
            openai_model="claude-opus-4-7",
            openai_reasoning_effort="medium",
            openai_endpoint_style="anthropic_messages",
            max_diff_chars=120000,
            max_output_tokens=1800,
            github_api_base="https://api.github.com",
            github_api_version="2022-11-28",
            openai_api_base="https://kuaipao.ai",
            dry_run=False,
        )

        with self.assertRaises(ReviewerError) as error:
            call_openai_review(config, "rules", "diff")

        self.assertIn("shared failure", str(error.exception))


class ReviewerScriptModeTests(unittest.TestCase):
    def test_reviewer_script_runs_in_file_mode(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "tools" / "reviewer.py"

        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Fetch a PR diff", result.stdout)


if __name__ == "__main__":
    unittest.main()
