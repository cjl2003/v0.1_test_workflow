# PR-Driven RTL Frontend Autoflow Design

## Goal

Build a phase-1 automation loop for the competition workflow that can:

- accept a natural-language frontend requirement from desktop Codex
- convert that requirement into a versioned request file and GitHub PR
- let GitHub-side GPT-5.4 clarify ambiguous requirements through PR comments
- let GPT-5.4 publish an execution plan for approval
- let local desktop Codex execute the approved plan
- verify `RTL + testbench + golden check`
- push code and run results back to GitHub for a final GPT-5.4 frontend review

This phase pauses for manual action when frontend review requests rework, and ends when the frontend requirement passes or fails.

## Scope

### In Scope

- desktop Codex request submission
- GitHub PR as the single collaboration surface
- PR comment-based clarification and approval flow
- GPT-5.4 requirement clarification
- GPT-5.4 plan generation
- local Codex execution of approved frontend work
- RTL compile, testbench self-check, and golden vector verification
- Git tags and run-result archiving for each completed local run
- GPT-5.4 frontend re-review after local execution

### Out of Scope

- remote server execution
- synthesis, STA, power, area, formal, LVS, or PnR
- automatic multi-round backend optimization
- fork PR support
- parallel execution of multiple frontend jobs
- automatic retry after runner failure

## Success Criteria

The phase-1 system is successful when one request can complete the following path:

1. A user gives a requirement to desktop Codex.
2. Codex writes `docs/requests/...md`, opens a PR, and sets the initial workflow state.
3. GPT-5.4 either asks blocking clarification questions or publishes a plan.
4. The user answers through PR comments and explicitly approves the plan with `/approve-plan`.
5. Local Codex picks up the approved plan, edits frontend files, and runs frontend verification.
6. Local Codex writes a run summary, creates a tag, and pushes the result.
7. GPT-5.4 reviews the changed frontend code and run results.
8. The PR either reaches `wf:frontend-passed`, pauses in `wf:rework-needed` until a user-issued `/codex-fix` requeues one minimal repair round, or ends in `wf:failed`.

## Architecture

The system is a PR-driven state machine with three actors:

- desktop Codex `submitter`
- desktop Codex `runner`
- GitHub-side GPT-5.4 workflows

GitHub PR is the only official handoff surface between these actors.

### Actor 1: Submitter

`submitter` is the foreground entry point used from the desktop Codex conversation.

Responsibilities:

- convert the user request into a versioned request document
- create a branch
- commit and push the request
- open a GitHub PR
- apply the initial workflow state

`submitter` does not wait for approval or execute code changes.

### Actor 2: Runner

`runner` is a background local automation that polls GitHub and executes approved plans.

Responsibilities:

- detect approved PR work items
- create an isolated local worktree
- read the current request, plan, and approval state
- modify RTL, testbench, and golden-check assets as required
- run local frontend verification
- write run artifacts and summaries
- commit, tag, and push successful frontend runs
- report failures without pushing partial implementation commits

`runner` does not clarify requirements and does not create plans.

### Actor 3: GitHub-Side GPT-5.4

GitHub-side GPT-5.4 is used only as planner and reviewer.

Responsibilities:

- read the request and related repository context
- ask clarification questions when requirements are ambiguous
- publish an execution plan when requirements are clear
- review local Codex frontend results after execution
- return a pass or rework decision

GPT-5.4 does not directly modify repository code, run local tools, or push commits.

## PR State Machine

Only one primary workflow label may exist on a PR at a time.

Primary labels:

- `wf:intake`
- `wf:needs-clarification`
- `wf:awaiting-plan-approval`
- `wf:codex-queued`
- `wf:codex-running`
- `wf:awaiting-gpt-review`
- `wf:rework-needed`
- `wf:frontend-passed`
- `wf:failed`

State rules:

- every new request PR starts at `wf:intake`
- GPT clarification output moves the PR to `wf:needs-clarification`
- GPT plan output moves the PR to `wf:awaiting-plan-approval`
- a valid `/approve-plan` issued after the latest `wf:plan` moves the PR to `wf:codex-queued`
- local runner claim moves the PR to `wf:codex-running`
- before the success push, the runner moves the PR to `wf:awaiting-gpt-review`
- GPT frontend acceptance moves the PR to `wf:frontend-passed`
- GPT frontend rejection moves the PR to `wf:rework-needed`
- a valid `/codex-fix` issued while the primary state is `wf:rework-needed` moves the PR to `wf:codex-queued` for one minimal repair round based on the latest `wf:gpt-review`
- any unrecoverable local or orchestration error moves the PR to `wf:failed`

## Data Model

### Request Document

Each request is stored in:

- `docs/requests/YYYY-MM-DD-<slug>.md`

The request document is the source of truth for the requested frontend work.
PR labels are the source of truth for workflow state.

Required content:

- request id
- title
- stage
- base branch
- work branch
- version
- goal
- in-scope items
- out-of-scope items
- acceptance criteria
- operating constraints

### Plan Comment

GPT-5.4 publishes the current execution plan in a PR comment marked with:

- `<!-- wf:plan -->`

Required plan sections:

- plan summary
- ordered task list
- expected file touch list
- done definition

The latest `wf:plan` comment is the only plan the local runner may execute.

### Clarification Comment

GPT-5.4 publishes blocking requirement questions in a PR comment marked with:

- `<!-- wf:clarification -->`

Questions must be minimal, explicit, and directly block planning.

### Run Result Document

Each successful local execution writes:

- `docs/runs/<request_id>/<timestamp>.md`

Required fields:

- request id
- run id
- version
- status
- tag
- commit
- commands executed
- pass/fail result per frontend verification stage
- artifact paths
- short notes

### Runner Summary Comment

Local Codex publishes execution status in a PR comment marked with:

- `<!-- wf:codex-run -->`

This comment contains:

- run id
- commit id when available
- tag when available
- verification summary
- failure step when applicable
- link or path reference to the run result document for successful runs

### GPT Review Comment

GPT-5.4 publishes frontend review results in a PR comment marked with:

- `<!-- wf:gpt-review -->`

Allowed review outcomes:

- `pass`
- `rework-needed`

## Command Protocol

Formal PR commands:

- `/answer ...`
- `/approve-plan`
- `/codex-fix`

Phase-1 required commands:

- `/answer ...`
- `/approve-plan`

Phase-1 optional but supported commands:

- `/codex-fix`

Behavior:

- `/answer ...` provides clarification input to GPT-5.4
- `/approve-plan` authorizes local execution only when it is issued after the latest `wf:plan`
- `/codex-fix` requeues a PR from `wf:rework-needed` into `wf:codex-queued` for exactly one manual minimal repair round based only on the latest `wf:gpt-review`

## Workflow Components

### Workflow 1: Request Planning

GitHub workflow: `request-plan.yml`

Triggers:

- PR opened
- PR synchronized while the primary state is `wf:intake` or `wf:needs-clarification`
- PR comment with `/answer ...`

Inputs:

- latest request document
- `docs/spec.md`
- `docs/golden_vectors.md`
- prior clarification comments
- user answers from PR comments

Outputs:

- updated `wf:clarification` comment or updated `wf:plan` comment
- state transition to either `wf:needs-clarification` or `wf:awaiting-plan-approval`

### Workflow 2: Command Routing

GitHub workflow: `command-router.yml`

Triggers:

- PR comments containing `/approve-plan`
- PR comments containing `/codex-fix`

Responsibilities:

- validate command format and author permission
- validate that `/approve-plan` is newer than the latest `wf:plan`
- move the PR into the correct workflow state only when that approval is valid
- validate that `/codex-fix` is issued while the PR is in `wf:rework-needed`
- validate that a latest `wf:gpt-review` comment exists before accepting `/codex-fix`
- move the PR to `wf:codex-queued` only for that minimal repair round
- avoid generating plan or review content itself

### Workflow 3: Frontend Review

GitHub workflow: `frontend-review.yml`

Triggers:

- PR updates after local runner push when state is already `wf:awaiting-gpt-review`
- updates to the latest `wf:codex-run` comment while state is `wf:awaiting-gpt-review`

Inputs:

- latest diff
- latest `wf:plan`
- latest `wf:codex-run`
- latest run result document

Outputs:

- updated `wf:gpt-review` comment
- state transition to `wf:frontend-passed` or `wf:rework-needed`

## Local Runner Execution Design

### Pickup Rules

The runner may only claim a PR when all of the following are true:

- primary state is `wf:codex-queued`
- the PR is from the same repository
- a latest `wf:plan` comment exists
- a valid `/approve-plan` command exists for the latest plan
- no other local job is currently active

Jobs are processed FIFO by queue time.

### Execution Steps

1. Fetch the latest PR metadata and branch state.
2. Create an isolated git worktree.
3. Load the request document and latest approved plan.
4. Transition the PR to `wf:codex-running`.
5. Edit only the files required for the approved frontend work.
6. Run frontend verification.
7. On success, write the run result document.
8. On success, commit changes and create a tag.
9. On success, transition the PR to `wf:awaiting-gpt-review`.
10. On success, push branch plus tag and then update the `wf:codex-run` comment.

### Rework Repair Round

When a PR is requeued from `wf:rework-needed` by a valid `/codex-fix`, the runner performs one manual minimal repair round.

For that repair round, the runner must:

- use the latest `wf:gpt-review` comment as the repair input
- limit edits to the smallest safe changes needed to address that review
- avoid reopening planning or broadening scope into a new implementation round
- return to the same verification and GPT review handoff path after the repair

### Verification Contract

Phase-1 local verification is fixed, not inferred.

Required commands:

- `sim/run_iverilog.bat`
- `python tools/check_golden.py`

Required pass conditions:

- RTL compile succeeds
- testbench output includes `Simulation Passed`
- golden vector verification succeeds

Any failed step marks the run as failed.

### Git Outputs

Successful local runs create:

- a commit containing implementation changes and run result files
- an annotated tag in the format `v0.1_frontend_pass_YYYYMMDD_HHMMSS_r001`

Failed local runs do not push partial code changes in phase 1.
Failed local runs do not commit `docs/runs/...md` in phase 1.

## Error Handling

### Clarification Failures

If GPT-5.4 cannot form a safe plan from current request information:

- it must publish a `wf:clarification` comment
- it must not publish a guessed execution plan

### Runner Failures

If the runner fails before successful verification:

- preserve the local worktree
- preserve local logs and patch data on Windows
- update `wf:codex-run` with the failure stage and summary
- do not write a repository run result document for that failed run
- move the PR to `wf:failed`

### Interrupted Jobs

If a runner job is interrupted and left in `wf:codex-running`:

- the next runner cycle marks it as interrupted
- the PR transitions to `wf:failed`
- no automatic resume occurs in phase 1

### Review Failures

If GPT-5.4 judges the frontend result insufficient:

- publish `wf:gpt-review` with `rework-needed`
- move the PR to `wf:rework-needed`
- do not auto-rerun or auto-replan
- allow a user-issued valid `/codex-fix` to requeue exactly one minimal repair round based on the latest `wf:gpt-review`

The system does not auto-replan or auto-rerun in phase 1.

## Logging and Retention

Repository retention:

- request documents
- successful run result summaries
- implementation commits
- tags
- machine-readable PR comments

Windows local retention:

- full command logs
- raw tool output
- preserved worktrees on failure
- local patch snapshots when needed

The repository stores summarized evidence only. Full logs remain on the Windows machine.

## Security and Safety Constraints

- only same-repo PRs are eligible for runner execution
- only one active local runner job is allowed at a time
- workflow commands must come from trusted authors
- execution requires explicit plan approval
- GPT-5.4 may propose edits, but only local Codex may execute them
- phase-1 runner should avoid unrelated cleanup or broad refactors

## Testing Strategy

### Workflow Testing

- open a request PR and confirm state becomes `wf:intake`
- confirm ambiguous requests produce `wf:clarification`
- answer with `/answer ...` and confirm GPT-5.4 updates the plan
- approve with `/approve-plan` and confirm state becomes `wf:codex-queued`
- after a `wf:rework-needed` review result, issue `/codex-fix` and confirm state returns to `wf:codex-queued`

### Runner Testing

- confirm runner picks only approved PRs
- confirm runner writes `wf:codex-running`
- confirm runner writes run result file and `wf:codex-run`
- confirm successful runs push a commit and the expected tag
- confirm failed runs set `wf:failed`

### Frontend Verification Testing

- confirm `sim/run_iverilog.bat` succeeds on a passing branch
- confirm `tools/check_golden.py` catches vector mismatches
- confirm GPT frontend review reads run summaries and changes the state correctly

## MVP Implementation Order

1. Implement request submission and request-file creation.
2. Implement GPT clarification and plan publication.
3. Implement direct GPT planning triggers for `/answer ...` and command routing for `/approve-plan` plus `/codex-fix`.
4. Implement local runner pickup, isolated worktree execution, and fixed frontend verification.
5. Implement run-summary persistence, commit, tag, and push behavior.
6. Implement GPT frontend re-review and final phase-1 state transitions.

## Open Phase-2 Extensions

These are intentionally deferred:

- remote server execution
- synthesis and STA orchestration
- area and power optimization loop
- backend artifact archiving
- automatic iterative optimization against competition targets

The phase-1 design must not depend on these future features.
