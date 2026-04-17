# Phase-2A Synthesis And Formal EC Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement phase-2A so the existing phase-1 PR-driven flow can continue from `wf:frontend-passed` into logic synthesis, mapped netlist generation, Formal EC, and baseline report collection without changing the user's desktop-first operating style.

**Architecture:** Start from a fresh worktree off `origin/main`, keep `python -m tools.runner_pickup` as the single local pickup entrypoint, and add the smallest backend baseline path instead of a full backend optimization system. Shared labels, markers, and GitHub helpers stay in `tools/workflow_lib.py`; a new local phase-2A runner handles `wf:backend-queued`; a new GitHub-side reviewer handles only pass/fail baseline review; desktop Codex continues translating the user's short desktop replies into PR comments and state changes so the user never has to work directly in GitHub.

**Tech Stack:** Python 3.11, GitHub Actions, GitHub REST API, local Codex CLI, Git worktrees, Markdown/JSON run artifacts

---

## File Map

- Modify: `tools/workflow_lib.py`
  - Add the minimal phase-2A labels, label metadata, comment markers, and shared parsing/render helpers.
- Modify: `tools/command_router.py`
  - Validate the minimal phase-2A slash command surface.
- Modify: `.github/workflows/command-router.yml`
  - Route the phase-2A backend-start command through the existing router workflow.
- Modify: `tools/runner_pickup.py`
  - Keep the phase-1 frontend path intact while adding dispatch for `wf:backend-queued`.
- Create: `tools/backend_baseline.py`
  - Phase-2A run ids, tags, artifact paths, manifest helpers, and comment/document rendering.
- Create: `tools/backend_runner.py`
  - Phase-2A queue claim, SSH gate, backend prompt construction, artifact validation, commit/tag/push, and `wf:backend-run` publication.
- Create: `tools/backend_review.py`
  - Phase-2A review prompt assembly, payload normalization, pass/fail review rendering, and PR state updates.
- Create: `.github/workflows/backend-review.yml`
  - Run the phase-2A baseline review from default-branch workflow code with the same secret/variable pattern already used on `origin/main`.
- Modify: `tests/test_workflow_lib.py`
  - Cover the new labels, markers, and command-router helpers.
- Modify: `tests/test_runner_flow.py`
  - Cover backend dispatch selection and any shared runner contract that changed.
- Create: `tests/test_backend_baseline.py`
  - Cover run ids, tags, artifact paths, and baseline rendering helpers.
- Create: `tests/test_backend_runner.py`
  - Cover SSH gate behavior, artifact contract validation, and backend queue claim logic with mocks.
- Create: `tests/test_backend_review.py`
  - Cover pass/fail review normalization and workflow-state updates.

## Guardrails

- Implementation must happen in a fresh worktree created from `origin/main`, not from the current stale root worktree.
- Keep the user contract unchanged: the user still only talks in the desktop Codex chat and still only gives short replies such as `继续后端`.
- Do not redesign phase-1. Extend it.
- Do not merge the request PR at `wf:frontend-passed` once phase-2A is enabled.
- Preserve the current GitHub-side OpenAI wiring already on `origin/main`. When editing workflow env blocks, confirm they still map `OPENAI_API_KEY` from `secrets.KUAIPAO_API_GPT` and do not accidentally reintroduce the old secret mapping from the stale local branch.
- Do not introduce auto-optimization, `wf:backend-plan`, stalled counters, or `continue-deeper` behavior in this implementation. Those belong to later phases.

### Task 1: Prepare A Clean Implementation Worktree

**Files:**
- No repo file required

- [ ] **Step 1: Fetch `origin/main` before touching code**

Run:

```powershell
git fetch origin
git rev-parse origin/main
```

Expected:

```text
The second command prints a commit id and exits 0.
```

- [ ] **Step 2: Create a dedicated worktree from `origin/main`**

Run:

```powershell
git worktree add ..\v0.1_test_workflow-phase2a origin/main -b codex/phase2a-baseline
```

Expected:

```text
Preparing worktree (new branch 'codex/phase2a-baseline')
The last line starts with "HEAD is now at" and exits 0.
```

- [ ] **Step 3: Verify the new worktree really starts from `origin/main`**

Run:

```powershell
Set-Location ..\v0.1_test_workflow-phase2a
git branch --show-current
git status --short
```

Expected:

```text
Current branch is codex/phase2a-baseline.
git status --short prints nothing.
```

- [ ] **Step 4: Capture the baseline test state before phase-2A changes**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected:

```text
The current phase-1 test suite passes from origin/main before any phase-2A edits.
```

### Task 2: Add Minimal Phase-2A Labels, Markers, And Shared State Helpers

**Files:**
- Modify: `tools/workflow_lib.py`
- Modify: `tests/test_workflow_lib.py`

- [ ] **Step 1: Write failing shared-state tests first**

Add tests like:

```python
from tools.workflow_lib import (
    MARKER_BACKEND_REVIEW,
    MARKER_BACKEND_RUN,
    PRIMARY_LABELS,
)


def test_primary_labels_constant_contains_phase2a_states(self) -> None:
    self.assertIn("wf:backend-queued", PRIMARY_LABELS)
    self.assertIn("wf:backend-running", PRIMARY_LABELS)
    self.assertIn("wf:backend-blocked", PRIMARY_LABELS)
    self.assertIn("wf:backend-passed", PRIMARY_LABELS)


def test_phase2a_marker_constants_are_stable(self) -> None:
    self.assertEqual(MARKER_BACKEND_RUN, "<!-- wf:backend-run -->")
    self.assertEqual(MARKER_BACKEND_REVIEW, "<!-- wf:backend-review -->")
```

- [ ] **Step 2: Run the targeted test file and confirm it fails for missing phase-2A primitives**

Run:

```powershell
python -m unittest tests.test_workflow_lib -v
```

Expected:

```text
FAIL or ERROR because the backend labels/markers do not exist yet.
```

- [ ] **Step 3: Add the minimal phase-2A labels and markers to `tools/workflow_lib.py`**

Implement only the states needed for synthesis + Formal EC baseline:

```python
PRIMARY_LABELS = (
    "wf:intake",
    "wf:needs-clarification",
    "wf:awaiting-plan-approval",
    "wf:codex-queued",
    "wf:codex-running",
    "wf:awaiting-gpt-review",
    "wf:rework-needed",
    "wf:frontend-passed",
    "wf:backend-queued",
    "wf:backend-running",
    "wf:awaiting-backend-review",
    "wf:backend-blocked",
    "wf:backend-passed",
    "wf:backend-failed",
    "wf:failed",
)

MARKER_BACKEND_RUN = "<!-- wf:backend-run -->"
MARKER_BACKEND_REVIEW = "<!-- wf:backend-review -->"
```

- [ ] **Step 4: Extend the label metadata so GitHub can create the new phase-2A labels**

Add entries in the same `PRIMARY_LABEL_META` map, for example:

```python
"wf:backend-queued": ("C2E0C6", "Phase-2A synthesis and Formal EC are queued for local Codex execution."),
"wf:backend-running": ("0E8A16", "Local Codex has claimed the phase-2A baseline run and is running."),
"wf:awaiting-backend-review": ("5319E7", "Phase-2A baseline artifacts are waiting for GPT review."),
"wf:backend-blocked": ("D93F0B", "Phase-2A is blocked on SSH or another prerequisite."),
"wf:backend-passed": ("006B75", "Phase-2A synthesis and Formal EC baseline passed."),
"wf:backend-failed": ("B60205", "Phase-2A synthesis or Formal EC baseline failed."),
```

- [ ] **Step 5: Re-run the shared-state tests and confirm they pass**

Run:

```powershell
python -m unittest tests.test_workflow_lib -v
```

Expected:

```text
PASS for the new phase-2A label and marker tests.
```

- [ ] **Step 6: Commit the shared phase-2A state primitives**

Run:

```powershell
git add tools/workflow_lib.py tests/test_workflow_lib.py
git commit -m "feat: add phase2a workflow states and markers"
```

### Task 3: Add Phase-2A Artifact And Baseline Rendering Helpers

**Files:**
- Create: `tools/backend_baseline.py`
- Create: `tests/test_backend_baseline.py`

- [ ] **Step 1: Write failing tests for phase-2A ids, tags, paths, and render helpers**

Add tests like:

```python
from tools.backend_baseline import (
    build_phase2a_run_id,
    build_phase2a_tag,
    build_phase2a_repo_dir,
    build_phase2a_local_dir,
    render_phase2a_summary_document,
    render_phase2a_run_comment,
)


def test_build_phase2a_tag_uses_ascii_format(self) -> None:
    tag = build_phase2a_tag("pass", "20260417_230500", "r003")
    self.assertEqual(tag, "v0.1_phase2a_pass_20260417_230500_r003")


def test_build_phase2a_repo_dir_is_request_scoped(self) -> None:
    path = build_phase2a_repo_dir("req-1", "phase2a-20260417_230500-r003")
    self.assertEqual(path.as_posix(), "docs/runs/req-1/backend/phase2a-20260417_230500-r003")


def test_render_phase2a_summary_document_mentions_synthesis_and_formal_ec(self) -> None:
    document = render_phase2a_summary_document(
        request_id="req-1",
        run_id="phase2a-20260417_230500-r003",
        version="r003",
        tag="v0.1_phase2a_pass_20260417_230500_r003",
        synthesis_status="pass",
        mapped_netlist_status="present",
        constraints_status="loaded",
        formal_ec_status="pass",
        baseline_metrics={
            "power": "240uW",
            "area": "8123um2",
            "timing": "worst setup slack = -0.08ns",
        },
    )
    self.assertIn("Formal EC", document)
    self.assertIn("240uW", document)
```

- [ ] **Step 2: Run the new baseline-helper test file and confirm it fails**

Run:

```powershell
python -m unittest tests.test_backend_baseline -v
```

Expected:

```text
ERROR because tools.backend_baseline does not exist yet.
```

- [ ] **Step 3: Create `tools/backend_baseline.py` with the normalized phase-2A data model**

Implement the minimal helpers needed by the runner and reviewer:

```python
from pathlib import Path


def build_phase2a_run_id(timestamp_token: str, version: str) -> str:
    return f"phase2a-{timestamp_token}-{version}"


def build_phase2a_tag(status_token: str, timestamp_token: str, version: str) -> str:
    return f"v0.1_phase2a_{status_token}_{timestamp_token}_{version}"


def build_phase2a_repo_dir(request_id: str, run_id: str) -> Path:
    return Path("docs") / "runs" / request_id / "backend" / run_id


def build_phase2a_local_dir(request_id: str, run_id: str) -> Path:
    return Path.home() / ".codex" / "backend_runs" / request_id / run_id
```

- [ ] **Step 4: Add Markdown/JSON render helpers for the phase-2A runner and reviewer**

Include helpers for:

```python
render_phase2a_summary_document(...)
render_phase2a_run_comment(...)
render_phase2a_review_comment(...)
```

The runner and reviewer should call these helpers instead of hand-writing comment bodies.

- [ ] **Step 5: Re-run the baseline-helper tests and confirm they pass**

Run:

```powershell
python -m unittest tests.test_backend_baseline -v
```

Expected:

```text
PASS for tag format, path helpers, and phase-2A rendering.
```

- [ ] **Step 6: Commit the phase-2A baseline helper module**

Run:

```powershell
git add tools/backend_baseline.py tests/test_backend_baseline.py
git commit -m "feat: add phase2a baseline artifact helpers"
```

### Task 4: Extend Command Routing For Phase-2A Start

**Files:**
- Modify: `tools/command_router.py`
- Modify: `.github/workflows/command-router.yml`
- Modify: `tests/test_workflow_lib.py`

- [ ] **Step 1: Add failing command-router tests for the phase-2A start command**

Add tests like:

```python
def test_continue_backend_requeues_after_frontend_pass(self) -> None:
    result = evaluate_command(
        command="/continue-backend",
        current_state="wf:frontend-passed",
        author_association="OWNER",
        command_created_at="2026-04-17T10:00:00Z",
        latest_plan_updated_at="2026-04-17T09:00:00Z",
        latest_gpt_review_updated_at="2026-04-17T09:30:00Z",
    )
    self.assertTrue(result.accepted)
    self.assertEqual(result.target_state, "wf:backend-queued")


def test_continue_backend_can_retry_from_backend_blocked(self) -> None:
    result = evaluate_command(
        command="/continue-backend",
        current_state="wf:backend-blocked",
        author_association="OWNER",
        command_created_at="2026-04-17T10:05:00Z",
        latest_plan_updated_at="2026-04-17T09:00:00Z",
        latest_gpt_review_updated_at="2026-04-17T09:30:00Z",
    )
    self.assertTrue(result.accepted)
    self.assertEqual(result.target_state, "wf:backend-queued")
```

- [ ] **Step 2: Run the command-router tests and confirm they fail**

Run:

```powershell
python -m unittest tests.test_workflow_lib.CommandRouterTests -v
```

Expected:

```text
FAIL or ERROR because `/continue-backend` is unsupported.
```

- [ ] **Step 3: Extend `evaluate_command()` for `/continue-backend` only**

Keep this phase small:

```python
if normalized.startswith("/continue-backend"):
    if current_state not in {"wf:frontend-passed", "wf:backend-blocked"}:
        return CommandDecision(
            False,
            None,
            "Current primary state must be wf:frontend-passed or wf:backend-blocked.",
        )
    return CommandDecision(True, "wf:backend-queued", "Backend start accepted.")
```

- [ ] **Step 4: Extend the workflow trigger so the router sees `/continue-backend`**

Update `.github/workflows/command-router.yml`:

```yaml
if: >-
  github.event.issue.pull_request &&
  (
    startsWith(github.event.comment.body, '/approve-plan') ||
    startsWith(github.event.comment.body, '/codex-fix') ||
    startsWith(github.event.comment.body, '/continue-backend')
  )
```

- [ ] **Step 5: Re-run the command-router tests and confirm they pass**

Run:

```powershell
python -m unittest tests.test_workflow_lib.CommandRouterTests -v
```

Expected:

```text
PASS for the phase-2A backend-start command cases.
```

- [ ] **Step 6: Commit the phase-2A command-routing extension**

Run:

```powershell
git add tools/command_router.py .github/workflows/command-router.yml tests/test_workflow_lib.py
git commit -m "feat: route phase2a backend start command"
```

### Task 5: Add A Phase-2A Backend Runner And Hook It Into `tools.runner_pickup`

**Files:**
- Create: `tools/backend_runner.py`
- Modify: `tools/runner_pickup.py`
- Create: `tests/test_backend_runner.py`
- Modify: `tests/test_runner_flow.py`

- [ ] **Step 1: Write failing backend-runner tests for the SSH gate and artifact contract**

Add tests like:

```python
def test_backend_runner_marks_blocked_when_ssh_file_is_missing(self) -> None:
    client = mock.Mock()
    candidate = BackendCandidate(
        pr_number=15,
        queue_time="2026-04-17T10:00:00Z",
        request_path="docs/requests/2026-04-17-phase2a-smoke.md",
        head_branch="request/2026-04-17-phase2a-smoke",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        with mock.patch("tools.backend_runner.SSH_INFO_PATH", Path(tmpdir) / "missing.txt"):
            execute_backend_candidate(client, candidate)
    client.set_primary_state.assert_called_with(15, "wf:backend-blocked")


def test_backend_runner_requires_phase2a_baseline_outputs(self) -> None:
    missing = validate_phase2a_outputs(
        local_dir=Path("C:/missing/local"),
        repo_dir=Path("docs/runs/req-test/backend/phase2a-1"),
    )
    self.assertIn("mapped.v", missing)
    self.assertIn("formal_ec_summary.md", missing)


def test_runner_pickup_dispatches_backend_candidate_when_state_is_backend_queued(self) -> None:
    ...
```

- [ ] **Step 2: Run the backend-runner and runner-flow tests and confirm they fail**

Run:

```powershell
python -m unittest tests.test_backend_runner -v
python -m unittest tests.test_runner_flow -v
```

Expected:

```text
ERROR because tools.backend_runner does not exist and tools.runner_pickup has no backend dispatch path.
```

- [ ] **Step 3: Create `tools/backend_runner.py` with the same local-runner shape as phase-1**

Keep the control flow parallel to the existing frontend runner:

```python
SSH_INFO_PATH = Path.home() / ".codex" / "secrets" / "huada_ssh.txt"


@dataclass(frozen=True)
class BackendCandidate:
    pr_number: int
    queue_time: str
    request_path: str
    head_branch: str


def execute_backend_candidate(client: GitHubClient, candidate: BackendCandidate) -> None:
    request_doc = read_text_file(worktree_path / candidate.request_path)
    prompt = build_phase2a_prompt(request_doc, run_id)
    codex_result = run_codex_exec(worktree_path, log_dir, prompt)
    missing = validate_phase2a_outputs(local_dir, repo_dir)
    if missing:
        raise WorkflowError(f"Phase-2A outputs missing required files: {missing}")
```

- [ ] **Step 4: Build a phase-2A Codex prompt that enforces the synthesis + Formal EC contract**

The prompt must require Codex to:

- read the latest request doc
- use the Huada remote skill chain
- read `C:\\Users\\lalala\\.codex\\secrets\\huada_ssh.txt`
- run **logic synthesis**
- generate a **mapped netlist**
- run **Formal EC** against the synthesized netlist
- collect synthesis power / area / timing summary reports
- save the local master package under `C:\\Users\\lalala\\.codex\\backend_runs\\` using the current request id and run id as nested directories
- write the slim repo artifacts under `docs/runs/` using the same request id and run id
- avoid P&R, STA signoff, LVS, SPEF, or automatic RTL optimization

The prompt builder should look like:

```python
def build_phase2a_prompt(request_doc: str, run_id: str) -> str:
    return (
        "You are the local desktop Codex backend runner for phase-2A.\\n"
        "Execute only logic synthesis, mapped netlist generation, Formal EC, and baseline report collection.\\n"
        "Use C:\\\\Users\\\\lalala\\\\.codex\\\\secrets\\\\huada_ssh.txt for SSH details.\\n"
        "Use the Huada remote skill chain to locate the correct synthesis and Formal EC tools.\\n"
        "Do not run place and route, signoff STA, LVS, SPEF, or any optimization loop.\\n"
    )
```

- [ ] **Step 5: Fail fast into `wf:backend-blocked` when SSH information is missing**

Implement the guard before `codex exec`:

```python
if not SSH_INFO_PATH.exists():
    client.upsert_marker_comment(
        pr_number,
        MARKER_BACKEND_RUN,
        render_phase2a_run_comment(
            status="blocked",
            run_id=run_id,
            synthesis_status="not-started",
            mapped_netlist_status="missing",
            constraints_status="unknown",
            formal_ec_status="not-started",
            notes="Waiting for refreshed SSH info.",
        ),
    )
    client.set_primary_state(pr_number, "wf:backend-blocked")
    return
```

- [ ] **Step 6: Validate artifacts after `codex exec` completes**

The runner must refuse success unless all of these exist:

```text
local_dir / "summary.md"
local_dir / "manifest.json"
local_dir / "mapped.v"
local_dir / "logs" / "synthesis.log"
local_dir / "logs" / "formal_ec.log"
repo_dir / "summary.md"
repo_dir / "manifest.json"
repo_dir / "reports" / "synthesis_power.rpt"
repo_dir / "reports" / "synthesis_area.rpt"
repo_dir / "reports" / "synthesis_timing_summary.rpt"
repo_dir / "reports" / "constraint_summary.md"
repo_dir / "reports" / "formal_ec_summary.md"
```

If any required file is missing, mark the round failed and keep the worktree for inspection.

- [ ] **Step 7: Commit, tag, and publish the phase-2A run in the same style as phase-1**

On success:

- set state to `wf:awaiting-backend-review`
- create an annotated backend tag using `build_phase2a_tag("pass", timestamp_token, version)` or `build_phase2a_tag("fail", ...)`
- push branch and tag
- upsert `<!-- wf:backend-run -->` with synthesis status, mapped netlist status, constraints status, Formal EC status, and baseline report headlines

- [ ] **Step 8: Hook the backend runner into `tools.runner_pickup.py` without breaking phase-1**

Add a dispatch split instead of rewriting the existing flow:

```python
if current_state == "wf:codex-queued":
    return build_frontend_candidate(client, pr)
if current_state == "wf:backend-queued":
    return build_backend_candidate(client, pr)
```

and:

```python
if candidate.queue_kind == "frontend":
    execute_candidate(client, candidate)
else:
    execute_backend_candidate(client, candidate)
```

- [ ] **Step 9: Re-run the backend-runner and runner-flow tests and confirm they pass**

Run:

```powershell
python -m unittest tests.test_backend_runner -v
python -m unittest tests.test_runner_flow -v
```

Expected:

```text
PASS for SSH-blocked handling, phase-2A artifact validation, and backend dispatch.
```

- [ ] **Step 10: Commit the local phase-2A runner**

Run:

```powershell
git add tools/backend_runner.py tools/runner_pickup.py tests/test_backend_runner.py tests/test_runner_flow.py
git commit -m "feat: add phase2a backend pickup and blocked handling"
```

### Task 6: Add GitHub-Side Phase-2A Review

**Files:**
- Create: `tools/backend_review.py`
- Create: `.github/workflows/backend-review.yml`
- Create: `tests/test_backend_review.py`

- [ ] **Step 1: Write failing backend-review tests for pass/fail baseline review**

Add tests like:

```python
from tools.backend_review import normalize_backend_review_payload


def test_normalize_backend_review_payload_for_pass(self) -> None:
    rendered = normalize_backend_review_payload(
        {
            "outcome": "pass",
            "summary": "Synthesis, mapped netlist generation, constraint loading, and Formal EC all pass.",
            "hard_findings": [],
            "baseline_warnings": ["Synthesis timing is still far from the 1GHz target."],
            "next_gate_recommendation": "ready-for-phase-2b",
        }
    )
    self.assertEqual(rendered.target_state, "wf:backend-passed")


def test_normalize_backend_review_payload_for_failed(self) -> None:
    rendered = normalize_backend_review_payload(
        {
            "outcome": "failed",
            "summary": "Formal EC did not pass.",
            "hard_findings": ["Formal EC summary shows a failing equivalence result."],
            "baseline_warnings": [],
            "next_gate_recommendation": "revise-rtl-before-phase-2b",
        }
    )
    self.assertEqual(rendered.target_state, "wf:backend-failed")
```

- [ ] **Step 2: Run the backend-review tests and confirm they fail**

Run:

```powershell
python -m unittest tests.test_backend_review -v
```

Expected:

```text
ERROR because tools.backend_review does not exist yet.
```

- [ ] **Step 3: Create `tools/backend_review.py` and keep the model output JSON-only**

Use the phase-1 reviewer shape as the template, but keep the scope strictly phase-2A:

```python
def build_backend_review_instructions() -> str:
    return '''
    Return JSON only.
    Allowed outcomes: "pass", "failed".
    Hard pass requires synthesis success, mapped netlist generation, constraint loading, and Formal EC success.
    You may include baseline warnings for synthesis power/area/timing, but do not propose an optimization loop here.
    '''
```

Normalize payloads into:

```python
{
    "outcome": "pass" | "failed",
    "summary": "Synthesis and Formal EC baseline summary.",
    "hard_findings": ["..."],
    "baseline_warnings": ["..."],
    "next_gate_recommendation": "ready-for-phase-2b" | "revise-rtl-before-phase-2b"
}
```

- [ ] **Step 4: Create `.github/workflows/backend-review.yml` from the phase-1 review pattern**

The workflow should:

- check out `refs/heads/${{ github.event.repository.default_branch }}`
- install requirements
- map `OPENAI_API_KEY` from the current `KUAIPAO_API_GPT` secret wiring already used on `origin/main`
- run on:
  - PR synchronize when the label is `wf:awaiting-backend-review`
  - issue comments containing `<!-- wf:backend-run -->`

Use a trigger block like:

```yaml
if: >-
  (
    github.event_name == 'pull_request' &&
    contains(github.event.pull_request.labels.*.name, 'wf:awaiting-backend-review')
  ) ||
  (
    github.event_name == 'issue_comment' &&
    github.event.issue.pull_request &&
    contains(github.event.comment.body, '<!-- wf:backend-run -->')
  )
```

- [ ] **Step 5: Re-run the backend-review tests and confirm they pass**

Run:

```powershell
python -m unittest tests.test_backend_review -v
```

Expected:

```text
PASS for pass/failed normalization and phase-2A review rendering.
```

- [ ] **Step 6: Commit the phase-2A review workflow**

Run:

```powershell
git add tools/backend_review.py .github/workflows/backend-review.yml tests/test_backend_review.py
git commit -m "feat: add phase2a backend review workflow"
```

### Task 7: End-To-End Validation Of The Phase-2A Baseline Gate

**Files:**
- Modify: any files required by earlier tasks only

- [ ] **Step 1: Run the full unit test suite from the clean worktree**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected:

```text
PASS for the existing phase-1 tests plus the new phase-2A test files.
```

- [ ] **Step 2: Verify the blocked path with no SSH file present**

Run:

```powershell
Remove-Item -LiteralPath "$HOME\\.codex\\secrets\\huada_ssh.txt" -ErrorAction SilentlyContinue
$pr = gh pr list --search "label:wf:backend-queued" --json number --jq '.[0].number'
python -m tools.runner_pickup --pr-number $pr
```

Expected:

```text
The PR moves to wf:backend-blocked and the latest wf:backend-run comment says SSH information is missing.
```

- [ ] **Step 3: Verify the success path with a real phase-2A Codex run**

Precondition:

```text
C:\Users\lalala\.codex\secrets\huada_ssh.txt contains fresh SSH information.
The request PR is open and already at wf:backend-queued.
```

Run:

```powershell
$pr = gh pr list --search "label:wf:backend-queued" --json number --jq '.[0].number'
python -m tools.runner_pickup --pr-number $pr
```

Expected:

```text
The worktree run creates a request-scoped local master package under C:\Users\lalala\.codex\backend_runs\, writes the slim baseline artifacts into that request's docs/runs backend directory, pushes a phase-2A tag, posts wf:backend-run, and moves the PR to wf:awaiting-backend-review.
```

- [ ] **Step 4: Verify backend review drives the final phase-2A transition correctly**

Run:

```powershell
$run = gh run list --workflow backend-review.yml --limit 1 --json databaseId --jq '.[0].databaseId'
gh run watch $run
```

Expected:

```text
One of these happens:
- outcome pass -> wf:backend-passed
- outcome failed -> wf:backend-failed
```

- [ ] **Step 5: Verify the review summary preserves baseline warnings without launching optimization**

Run:

```powershell
$pr = gh pr list --search "label:wf:backend-passed" --json number --jq '.[0].number'
gh pr view $pr --comments
```

Expected:

```text
The latest wf:backend-review comment can mention bad synthesis timing/power/area as warnings, but it does not publish wf:backend-plan and does not requeue another backend round automatically.
```

- [ ] **Step 6: Commit any final fixes that were needed during validation**

Run:

```powershell
git add -A
git commit -m "fix: close remaining phase2a baseline gaps"
```

## Self-Review Checklist

- Every phase-2A state in the design maps to a concrete implementation task above.
- The same request PR stays open throughout the plan; there is no task that merges at `wf:frontend-passed`.
- The user still only interacts through the desktop Codex chat; PR slash commands are internal transport, not a new user burden.
- The plan does not introduce auto-optimization, stalled counters, or `wf:backend-plan`.
- Logic synthesis, mapped netlist generation, constraint loading, Formal EC, and baseline report collection are all covered explicitly.
- The current `origin/main` OpenAI secret wiring is explicitly preserved while editing workflows.
