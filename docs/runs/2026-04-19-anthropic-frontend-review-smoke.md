# Anthropic Frontend Review Smoke

## Summary

- Purpose: exercise the GitHub-side `Frontend Review` workflow with `OPENAI_ENDPOINT_STYLE=anthropic_messages`.
- PR: `#24`
- Branch: `codex/anthropic-workflow-smoke`
- This is a smoke-only artifact, not a product deliverable.

## Inputs

- `OPENAI_API_BASE=https://kuaipao.ai`
- `OPENAI_ENDPOINT_STYLE=anthropic_messages`
- `OPENAI_MODEL=claude-opus-4-6`
- `OPENAI_REVIEW_MODEL=claude-opus-4-6`

## Verified Context

- `Request Planning` already succeeded for this provider combination and posted `wf:plan` on PR `#24`.
- Diagnostic smoke confirmed an Anthropic Messages-style response shape for `claude-opus-4-6`.
- This step does not change workflow YAML. It only prepares the minimum PR artifact needed to drive `frontend-review.yml`.

## Local Codex Action

- Reused the existing temporary smoke PR and planner output.
- Added this run-result document so the latest `wf:codex-run` marker can point at a stable text artifact on the PR head.
- Next GitHub action should set the PR to `wf:awaiting-gpt-review` and trigger `Frontend Review`.

## Expected Smoke Result

- Success for this smoke means the reviewer path reaches the Anthropic-compatible model call and posts or updates the machine-readable review comment.
- A content-level review outcome of either `pass` or `rework-needed` is acceptable for smoke purposes.
- A provider-side failure is only useful if it clearly comes from reviewer execution and not from URL/protocol mismatch.
