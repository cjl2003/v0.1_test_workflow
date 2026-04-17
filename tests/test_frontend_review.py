import unittest
from unittest import mock

from tools import frontend_review


class FrontendReviewTests(unittest.TestCase):
    def test_partition_changed_paths_treats_request_and_run_docs_as_artifacts(self) -> None:
        diff_text = """\
diff --git a/README.md b/README.md
index 1111111..2222222 100644
--- a/README.md
+++ b/README.md
diff --git a/docs/requests/2026-04-17-readme-md.md b/docs/requests/2026-04-17-readme-md.md
new file mode 100644
--- /dev/null
+++ b/docs/requests/2026-04-17-readme-md.md
diff --git a/docs/runs/req-20260417-030551-readme-md/20260417_041824.md b/docs/runs/req-20260417-030551-readme-md/20260417_041824.md
new file mode 100644
--- /dev/null
+++ b/docs/runs/req-20260417-030551-readme-md/20260417_041824.md
"""
        scoped_paths, artifact_paths = frontend_review.partition_changed_paths(diff_text)

        self.assertEqual(scoped_paths, ["README.md"])
        self.assertEqual(
            artifact_paths,
            [
                "docs/requests/2026-04-17-readme-md.md",
                "docs/runs/req-20260417-030551-readme-md/20260417_041824.md",
            ],
        )

    def test_build_review_instructions_excludes_phase1_artifacts_from_scope_findings(self) -> None:
        instructions = frontend_review.build_review_instructions()

        self.assertIn("docs/requests/", instructions)
        self.assertIn("docs/runs/", instructions)
        self.assertIn("do not treat them as scope violations", instructions)

    def test_load_review_context_reads_run_result_via_github_client(self) -> None:
        latest_plan = {
            "body": "<!-- wf:plan -->\n## Frontend Plan",
            "created_at": "2026-04-17T03:12:36Z",
            "updated_at": "2026-04-17T03:12:36Z",
        }
        latest_run = {
            "body": (
                "<!-- wf:codex-run -->\n"
                "## Local Codex Run\n"
                "- Run Result Path: `docs/runs/req-1/20260417_041824.md`"
            ),
            "created_at": "2026-04-17T04:21:08Z",
            "updated_at": "2026-04-17T04:21:08Z",
        }
        client = mock.Mock()
        client.list_issue_comments.return_value = [latest_plan, latest_run]
        client.fetch_pull_request_diff.return_value = "diff --git a/README.md b/README.md"
        client.fetch_pull_request_file_text.return_value = "# Frontend Run Result"

        context = frontend_review.load_review_context(11, client)

        client.fetch_pull_request_file_text.assert_called_once_with(
            11, "docs/runs/req-1/20260417_041824.md"
        )
        self.assertIn("# Frontend Run Result", context)


if __name__ == "__main__":
    unittest.main()
