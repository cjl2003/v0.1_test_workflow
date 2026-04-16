# Local Codex + GPT Review Design

## Goal

Replace the server-side auto-fix path with a true hybrid loop:

- desktop Codex writes code locally with local skills
- GitHub Actions runs GPT review remotely on every PR update

## Design

### Stage 1: review

- GitHub Actions continues to trigger on PR updates.
- `tools/reviewer.py` fetches the PR diff and posts `RTL Auto Review`.
- The reviewer model is configured through `OPENAI_REVIEW_MODEL`.

### Stage 2: request queue

- A trusted PR comment beginning with `/codex-fix` does not edit code on the
  server.
- Instead, `.github/workflows/codex-fix.yml` adds label
  `codex-fix-pending` and posts an acknowledgement comment.

### Stage 3: local Codex execution

- A desktop Codex automation running on this machine watches for open PRs labeled
  `codex-fix-pending`.
- It checks out the PR branch locally, uses local skills, applies minimal fixes,
  verifies, commits, and pushes.
- A successful push retriggers Stage 1 automatically.

## Safety

- Only same-repo PRs are in scope for the local fix loop.
- Only files already changed in the PR may be edited.
- The local automation must follow `.ai/desktop_codex_fix_rules.md`.
- Failed or ambiguous fix attempts should be labeled `codex-fix-failed`.
