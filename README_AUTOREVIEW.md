# PR Auto Review for RTL / Verilog

## What this system does now

This repository now uses a true hybrid two-stage loop:

1. **GitHub Actions + GPT reviewer**
   - When a PR is opened or updated, GitHub Actions runs `tools/reviewer.py`.
   - The script fetches the PR diff and asks the configured review model to do
     RTL / Verilog review.
   - The result is written back to the PR as a single updatable comment.

2. **Desktop Codex fix loop**
   - When a trusted reviewer comments `/codex-fix` on the PR, GitHub does not
     fix code on the server anymore.
   - Instead, GitHub marks the PR with `codex-fix-pending`.
   - A local desktop Codex automation watches for that label, checks out the PR
     branch on this machine, edits code using local skills, verifies, commits,
     and pushes.
   - That push triggers the GPT review workflow again.

This separation is intentional:

- **Codex** writes and edits code locally, with local skills.
- **GPT-5.4** reviews code in GitHub Actions.

## Files

- `.github/workflows/auto-review.yml`
  - GitHub Actions workflow for PR review.
- `.github/workflows/codex-fix.yml`
  - GitHub Actions workflow that turns `/codex-fix` into a queued local fix
    request by labeling the PR.
- `tools/reviewer.py`
  - Fetches PR metadata and diff, calls the review model, and updates the PR
    comment.
- `.ai/reviewer_rules.md`
  - RTL review rubric for the GPT reviewer.
- `.ai/desktop_codex_fix_rules.md`
  - Local repair rules for the desktop Codex automation.
- `requirements.txt`
  - Python dependencies for the review workflow.
- `.env.example`
  - Example environment configuration for local script runs.
- `README_AUTOREVIEW.md`
  - Setup and operating notes.

## Architecture

### Stage 1: GPT review in GitHub

- Trigger: `pull_request` `opened` / `synchronize` / `reopened`
- Workflow: `.github/workflows/auto-review.yml`
- Script: `tools/reviewer.py`
- Output: `RTL Auto Review` PR comment

### Stage 2: Codex fix on the local desktop

- Trigger command in PR: `/codex-fix`
- Workflow: `.github/workflows/codex-fix.yml`
- Server behavior: add label `codex-fix-pending`
- Local behavior: desktop Codex automation sees the label, fixes code, commits,
  pushes, and lets Stage 1 run again

## GitHub Secrets and repository variables

### Required secret

- `OPENAI_API_KEY`
  - Used by `tools/reviewer.py` in GitHub Actions.

### Built-in token

- `GITHUB_TOKEN`
  - GitHub injects this automatically for Actions jobs.

### Repository variables for the reviewer

- `OPENAI_API_BASE`
  - Example: `http://101.43.9.6:3000/v1`
- `OPENAI_REVIEW_MODEL`
  - Recommended for this setup: `gpt-5.4`
- `OPENAI_MODEL`
  - Optional fallback if `OPENAI_REVIEW_MODEL` is not set
- `OPENAI_ENDPOINT_STYLE`
  - `auto`, `responses`, or `chat_completions`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_MAX_OUTPUT_TOKENS`
- `MAX_DIFF_CHARS`

### Local desktop Codex configuration

The fixer is no longer configured through GitHub repository variables.

Instead, it is configured by the local Codex desktop automation itself:

- automation model: use a Codex model such as `gpt-5.2-codex`
- local skills: use the desktop Codex skill system
- local verify command: typically `git diff --check`, or a stronger RTL lint /
  syntax command if you have one

## Required local automation

This repository now expects a local desktop Codex automation to be active.

That automation should:

1. Look for open PRs labeled `codex-fix-pending`
2. Read the latest `RTL Auto Review` comment
3. Read the latest `/codex-fix` instruction
4. Checkout the PR branch locally
5. Fix only files already changed in the PR
6. Follow `.ai/desktop_codex_fix_rules.md`
7. Verify, commit, push
8. Replace the label:
   - success: `codex-fix-applied`
   - failure: `codex-fix-failed`

## First-time enablement

1. Push these files to the repository default branch.
2. Configure GitHub Actions secrets and variables:
   - `OPENAI_API_KEY`
   - `OPENAI_API_BASE`
   - `OPENAI_REVIEW_MODEL=gpt-5.4`
3. Confirm `Settings -> Actions -> General -> Workflow permissions` allows PR
   comment writes.
4. Enable the local desktop Codex automation on this machine.

## Day-to-day usage

### Normal PR review

1. Push your RTL changes to a branch.
2. Open a PR to `main`.
3. Wait for `RTL PR Auto Review`.
4. Read the `RTL Auto Review` comment.

### Ask Codex to fix

If you want the desktop Codex agent to try a repair, comment this on the PR:

```text
/codex-fix
```

Or add a short instruction:

```text
/codex-fix Please keep the patch minimal and only touch the new RTL file.
```

After that:

1. GitHub labels the PR as `codex-fix-pending`
2. Local desktop Codex picks it up
3. Codex pushes a fix commit
4. GitHub automatically runs the GPT reviewer again

## How to test

### Test the reviewer

1. Open a small PR that changes a `.v` or `.sv` file.
2. Wait for `RTL PR Auto Review`.
3. Confirm the PR timeline contains `RTL Auto Review`.

### Test the full Codex -> GPT loop

1. Open a same-repo PR with an intentionally fixable RTL issue.
2. Wait for the initial `RTL Auto Review` comment.
3. Add `/codex-fix`.
4. Confirm the PR gets label `codex-fix-pending`.
5. Wait for the local desktop Codex automation to:
   - commit and push a fix
   - change the label from `codex-fix-pending` to `codex-fix-applied` or
     `codex-fix-failed`
6. Confirm GitHub runs `RTL PR Auto Review` again on the pushed commit.

## Why this is different from the previous server-side version

The old implementation used a GitHub Actions job to generate and push fixes
directly on the server.

That version did not satisfy the real requirement of:

- **desktop Codex writes code**
- **GPT reviews**

The current design does satisfy that requirement:

- GitHub server: reviewer only
- Local desktop Codex: code editing and local skills

## Limitations

- The local Codex loop only works while this desktop automation is active.
- Fork PRs are not part of the minimal local-fix design.
- Reviewer comments can still contain false positives or inconsistent findings.
- The local fixer should still be constrained to minimal safe edits.
- The default verification command is still lightweight unless you strengthen it.
