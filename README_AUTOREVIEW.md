# PR Auto Review for RTL / Verilog

## What this system does

This repository now contains a minimal PR auto-review path for RTL projects:

1. A GitHub Actions workflow triggers on `pull_request` `opened`,
   `synchronize`, and `reopened`.
2. `tools/reviewer.py` reads the PR number, repository, and tokens from
   environment variables.
3. The script fetches the PR metadata and unified diff from the GitHub REST API.
4. The script sends the diff to the OpenAI Responses API using RTL-specific
   review rules from `.ai/reviewer_rules.md`.
5. The script creates or updates a single PR timeline comment with the review.

The default implementation is intentionally small:

- GitHub comment type: issue-style PR timeline comment
- Review source: PR unified diff
- Review target: Verilog / SystemVerilog / RTL risks
- Comment behavior: update the previous auto-review comment on each new push

## Files

- `.github/workflows/auto-review.yml`
  - GitHub Actions entry point that installs dependencies and runs the reviewer
    when a PR is opened or updated.
- `tools/reviewer.py`
  - Main reviewer script. Fetches PR data from GitHub, calls the OpenAI
    Responses API, and posts the result back to the PR.
- `.ai/reviewer_rules.md`
  - The RTL-specific review rubric passed to the model.
- `requirements.txt`
  - Minimal Python dependencies for local runs and GitHub Actions.
- `.env.example`
  - Example local environment configuration.
- `README_AUTOREVIEW.md`
  - Setup, testing, and extension notes.

## GitHub Secrets and variables

### Required secret

- `OPENAI_API_KEY`
  - OpenAI API key used by `reviewer.py`.

### Built-in token

- `GITHUB_TOKEN`
  - No manual secret creation is normally needed.
  - GitHub Actions injects this automatically.
  - The workflow passes it into `reviewer.py` as `GITHUB_TOKEN`.

### Optional repository variables

You can keep defaults, but these repo variables are supported:

- `OPENAI_API_BASE`
  - Default in code: `https://api.openai.com/v1`
  - For OpenAI-compatible gateways, set this to the gateway's API base URL.
- `OPENAI_MODEL`
  - Default in code: `gpt-5.4`
- `OPENAI_ENDPOINT_STYLE`
  - Default in code: `auto`
  - Supported values: `auto`, `responses`, `chat_completions`
  - Use `chat_completions` when your gateway does not support `/v1/responses`.
- `OPENAI_REASONING_EFFORT`
  - Default in code: `medium`
- `OPENAI_MAX_OUTPUT_TOKENS`
  - Default in code: `1800`
- `MAX_DIFF_CHARS`
  - Default in code: `120000`

## First-time enablement

1. Commit these files to the repository default branch.
2. In GitHub repository settings, enable Actions if it is disabled.
3. In `Settings -> Secrets and variables -> Actions`, create the secret
   `OPENAI_API_KEY`.
4. In `Settings -> Actions -> General -> Workflow permissions`, make sure the
   workflow token can write PR comments. If your repo policy is restrictive,
   switch to `Read and write permissions`.
5. Open or update an internal PR and confirm that `RTL PR Auto Review` runs.

## How to test

### Test in GitHub

1. Push these files to the default branch.
2. Create a small PR that changes one or two `.v` / `.sv` files.
3. Wait for the `RTL PR Auto Review` workflow to finish.
4. Check the PR timeline for a comment starting with `RTL Auto Review`.
5. Push one more commit to the PR and confirm the same comment is updated.

### Test locally

1. Copy `.env.example` to `.env` and fill in real values.
2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Run a dry run:

```bash
python tools/reviewer.py 123 --dry-run
```

The dry run prints the generated comment body without writing back to GitHub.

## How to extend to "Codex fix -> GPT re-review"

One practical next step is to split the flow into two workflows:

1. Keep `auto-review.yml` as the "review" workflow.
2. Add a second workflow triggered by a label, slash command, or manual dispatch
   such as `codex-fix`.
3. That second workflow reads the latest auto-review comment, asks Codex (or
   another code-writing agent) to patch the PR branch, and pushes a fix commit.
4. The new commit triggers `pull_request.synchronize`.
5. The existing `auto-review.yml` runs again and produces the next review pass.

Recommended guardrails for the multi-round version:

- Only run auto-fix on trusted branches or organization members.
- Limit the maximum loop count to avoid fix/review ping-pong.
- Store the latest review marker in the PR comment so the fix workflow knows
  which findings were already addressed.
- Require at least one deterministic verification step before pushing the fix.

## Default assumptions and limitations

- This implementation assumes GitHub.com-style REST APIs.
- The workflow is based on `pull_request`, exactly as requested.
- For PRs from forks, GitHub does not pass regular secrets such as
  `OPENAI_API_KEY` to the runner, and `GITHUB_TOKEN` is restricted. In that
  case, this minimal workflow may not be able to call OpenAI or write comments.
- If you need secure external-contributor support later, the usual next step is
  to redesign around `pull_request_target` or a two-stage artifact workflow.
- For third-party OpenAI-compatible gateways, verify the transport is trusted
  and encrypted before sending repository diffs through it.
