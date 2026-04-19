import unittest
from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "frontend-review.yml"
)


class FrontendReviewWorkflowTests(unittest.TestCase):
    def test_pull_request_path_checks_out_pr_head(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("- name: Check out PR head on pull_request", workflow_text)
        self.assertIn("if: github.event_name == 'pull_request'", workflow_text)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha }}", workflow_text)

    def test_issue_comment_path_keeps_default_branch_checkout(self) -> None:
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("- name: Check out default branch workflow code on issue_comment", workflow_text)
        self.assertIn("if: github.event_name == 'issue_comment'", workflow_text)
        self.assertIn(
            "ref: refs/heads/${{ github.event.repository.default_branch }}", workflow_text
        )


if __name__ == "__main__":
    unittest.main()
