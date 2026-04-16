# Desktop Codex Fix Rules

This file defines the local repair rules for the desktop Codex automation that
responds to `/codex-fix`.

## Goal

Use the latest GPT review comment to apply the smallest safe code change on the
current PR branch, then push the fix so GitHub can run the reviewer again.

## Allowed Scope

- Only act on open PRs labeled `codex-fix-pending`.
- Only edit files that are already changed in that PR.
- Only edit text files that the local Codex session can read safely.
- Prefer RTL / Verilog / SystemVerilog fixes over unrelated cleanup.
- Do not reformat unrelated files.
- Do not rename files or create broad refactors unless the review explicitly
  requires it and the change remains minimal.

## Repair Priorities

1. P1 / high-confidence correctness bugs
2. Reset / clocking / blocking-vs-nonblocking / latch / width issues
3. Synthesis-safety issues
4. Small clarity fixes directly tied to the latest GPT findings

## Safety Rules

- Treat the latest `RTL Auto Review` comment as guidance, not ground truth.
- If the GPT review is internally inconsistent, prefer the code and the PR diff.
- If a requested fix appears unsafe, ambiguous, or requires broad design changes,
  stop and mark the PR as `codex-fix-failed` instead of guessing.
- Never overwrite unrelated user changes.

## Verification

- Run the repository's configured minimal verification command before commit.
- If verification fails, do not push.
- Explain the failure briefly in the PR comment and switch the label from
  `codex-fix-pending` to `codex-fix-failed`.

## Git Behavior

- Commit message format:

```text
fix: apply desktop Codex fixes for PR #<number>
```

- After a successful push:
  - remove `codex-fix-pending`
  - add `codex-fix-applied`

- After an unsuccessful attempt:
  - remove `codex-fix-pending`
  - add `codex-fix-failed`
