# Actions Node24 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade GitHub Actions workflow dependencies off deprecated Node.js 20-backed action versions.

**Architecture:** Keep behavior unchanged and only update workflow action versions in existing CI files. Guard the change with a unit test that reads the tracked workflow YAML files and rejects regressions back to deprecated major versions.

**Tech Stack:** GitHub Actions YAML, Python `unittest`, repository workflow tests

---

### Task 1: Add workflow version regression test

**Files:**
- Modify: `tests/test_workflow_lib.py`
- Test: `tests/test_workflow_lib.py`

- [ ] **Step 1: Write the failing test**

```python
def test_workflows_use_node24_compatible_action_versions(self) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workflow_lib.WorkflowFilesTests.test_workflows_use_node24_compatible_action_versions -v`
Expected: FAIL because workflow files still reference `actions/checkout@v4` and `actions/setup-python@v5`.

- [ ] **Step 3: Write minimal implementation**

```yaml
uses: actions/checkout@v6
uses: actions/setup-python@v6
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workflow_lib.WorkflowFilesTests.test_workflows_use_node24_compatible_action_versions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_workflow_lib.py .github/workflows/*.yml docs/superpowers/plans/2026-04-17-actions-node24-upgrade.md
git commit -m "chore: upgrade workflow actions for node24"
```

### Task 2: Run workflow regression suite

**Files:**
- Test: `tests/test_workflow_lib.py`

- [ ] **Step 1: Run targeted regression suite**

Run: `python -m unittest tests.test_workflow_lib tests.test_frontend_review tests.test_reviewer -v`
Expected: PASS with no workflow-version regressions.

- [ ] **Step 2: Verify no unintended files changed**

Run: `git status --short`
Expected: Only the workflow files, plan doc, and test file are modified for this task.
