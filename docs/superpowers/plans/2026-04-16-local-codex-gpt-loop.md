# Local Codex + GPT Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move fix generation from GitHub Actions to desktop Codex while keeping GPT review in GitHub.

**Architecture:** GitHub queues `/codex-fix` requests with labels; a local desktop Codex automation consumes the queue, edits code locally with skills, pushes a fix commit, and lets the PR reviewer rerun.

**Tech Stack:** GitHub Actions, GitHub CLI, Python reviewer script, desktop Codex heartbeat automation

---

### Task 1: Split reviewer model configuration

**Files:**
- Modify: `.github/workflows/auto-review.yml`
- Modify: `tools/reviewer.py`
- Test: `tests/test_reviewer.py`

- [ ] Update the review workflow to pass `OPENAI_REVIEW_MODEL`.
- [ ] Update `tools/reviewer.py` to prefer `OPENAI_REVIEW_MODEL` over `OPENAI_MODEL`.
- [ ] Add a unit test covering the override behavior.
- [ ] Run `python -m unittest tests.test_reviewer -v`.

### Task 2: Replace server-side fixer with a request queue

**Files:**
- Modify: `.github/workflows/codex-fix.yml`
- Delete: `tools/codex_fix.py`
- Delete: `tests/test_codex_fix.py`

- [ ] Rewrite `codex-fix.yml` so it labels PRs instead of editing code.
- [ ] Create / maintain labels `codex-fix-pending`, `codex-fix-applied`, and `codex-fix-failed`.
- [ ] Remove the obsolete server-side fixer script and its tests.

### Task 3: Add local Codex operating rules and docs

**Files:**
- Create: `.ai/desktop_codex_fix_rules.md`
- Modify: `README_AUTOREVIEW.md`
- Modify: `AUTOREVIEW_STATUS_CN.md`

- [ ] Document the local repair boundaries.
- [ ] Update the repository README to describe the new hybrid loop.
- [ ] Update the Chinese status handoff document to match the new architecture.

### Task 4: Create desktop Codex automation

**Files:**
- No repo file required

- [ ] Create an active desktop automation that watches for `codex-fix-pending`.
- [ ] Configure it to use a Codex model and local RTL skill(s).
- [ ] Make it verify, commit, push, and relabel PRs.

### Task 5: End-to-end validation

**Files:**
- Create: temporary test branch / PR

- [ ] Open a test PR with a small RTL issue.
- [ ] Confirm Stage 1 review posts a GPT comment.
- [ ] Comment `/codex-fix`.
- [ ] Confirm GitHub labels the PR `codex-fix-pending`.
- [ ] Confirm desktop Codex pushes a fix commit.
- [ ] Confirm the PR triggers a fresh GPT review.
