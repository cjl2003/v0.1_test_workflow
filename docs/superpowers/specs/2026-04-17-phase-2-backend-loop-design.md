# Phase-2A Synthesis And Formal EC Baseline Design

## Goal

Extend the current phase-1 frontend loop into the **first backend checkpoint** only.

This phase, now explicitly called **phase-2A**, is limited to:

- pausing after `wf:frontend-passed`
- waiting for a user-issued desktop approval to start backend work
- connecting to the Huada Jiutian remote server from desktop Codex
- running **logic synthesis**
- producing a mapped netlist
- running **Formal EC** between RTL and the synthesized netlist
- pulling back a reproducible local package to Windows
- publishing a slim backend baseline result set back to the same request PR
- letting GPT-5.4 review the baseline package and summarize whether the hard phase-2A gate passed

This document **does not** define:

- auto-optimization loops
- place and route
- signoff STA
- LVS / SPEF / physical verification
- phase-2B or phase-2C implementation details

---

## Relationship To Existing Phase-1

Current phase-1 already covers:

- request creation
- clarification
- plan generation
- local frontend execution
- frontend verification
- GPT-5.4 frontend re-review

Phase-2A starts **only after** that existing flow reaches `wf:frontend-passed`.

Important boundary:

- in the current repository, `wf:frontend-passed` is the successful end of phase-1
- in the combined system, `wf:frontend-passed` is the **handoff checkpoint** into phase-2A
- phase-2A must not start on its own from that checkpoint

---

## Why Phase-2 Was Narrowed To Phase-2A

The contest spec requires the full digital backend chain, but the required steps are not all equal in dependency or automation value.

The clean dependency order is:

1. **phase-2A**
   - logic synthesis
   - mapped netlist generation
   - Formal EC
   - baseline report collection

2. **phase-2B**
   - place and route
   - STA across required corners
   - power / area / timing main optimization loop

3. **phase-2C**
   - LVS
   - SPEF
   - physical verification and final signoff-style checks

Therefore phase-2A is intentionally the smallest backend stage that proves:

- this RTL can enter the backend tool chain
- synthesis constraints are actually being read
- synthesis output is functionally consistent with RTL
- baseline synthesis reports can be archived for later decisions

---

## User Experience Contract

The user must continue to interact only through the desktop Codex conversation.

Phase-2A must follow the already-accepted phase-1 operating style, not introduce a second user workflow.

The user must not be required to:

- open the PR to type commands
- inspect workflow pages
- run remote-shell commands manually
- copy logs off the server manually
- interpret synthesis / Formal EC reports directly before the system summarizes them

The only phase-2A user action should be a short desktop reply such as:

- `继续后端`

Desktop Codex is responsible for translating that desktop reply into the PR state and backend execution action.

---

## Start Gate

### Rule 1: Phase-2A Never Starts Automatically

After phase-1 reaches `wf:frontend-passed`, the system must stop and wait.

Desktop Codex must report back in the desktop conversation with a short summary of:

- current request / PR
- frontend pass result
- whether phase-2A synthesis / Formal EC is ready to start

Phase-2A execution may begin only after the user replies:

- `继续后端`

This explicit approval is required because:

- the Huada Jiutian server connection is time-sensitive
- SSH information may expire or rotate
- even this smaller backend step consumes remote resources and time

### Rule 2: Approval Is A Desktop Approval, Not A PR Burden

The user does not need to type a GitHub PR command directly.

Desktop Codex should:

1. read the user's desktop reply
2. translate it into the appropriate internal PR / workflow action
3. start phase-2A on the user's behalf

### Rule 3: The Request PR Must Stay Open Through Phase-2A

Once a request enters phase-2A, the same request PR must remain open while synthesis and Formal EC run.

In particular:

- `wf:frontend-passed` is a handoff checkpoint, not an auto-merge point
- the PR must not be merged just because phase-1 succeeded
- the PR should remain open until phase-2A reaches a terminal backend state and the user decides the next step

---

## Scope Of Phase-2A

### Hard Deliverables

Phase-2A must produce all of the following:

- a successful logic synthesis run
- a mapped netlist
- proof that the synthesis constraints were loaded normally
- a successful Formal EC result against the synthesized netlist
- a reproducible Windows-side run package
- a slim GitHub-side baseline artifact set for PR review

### Baseline Reports To Collect

Phase-2A must also collect the synthesis-stage baseline reports that naturally exist at this stage:

- synthesis power
- synthesis area
- synthesis timing summary

These reports are required for visibility and later phase decisions, but **phase-2A does not turn them into a multi-round auto-optimization loop**.

### Non-Goals For Phase-2A

Phase-2A explicitly does **not** do the following:

- automatic repeated RTL optimization for synthesis PPA
- place and route
- post-route STA
- LVS
- SPEF extraction
- final physical verification
- phase-2B or phase-2C signoff decisions

If the synthesis reports look obviously catastrophic, desktop Codex may stop before phase-2B and ask whether RTL should be revised first, but phase-2A itself is still a **baseline gate**, not an optimizer.

---

## Remote Access Model

### SSH Source Of Truth

The current SSH information for the Huada Jiutian server must be stored locally at:

- `C:\Users\lalala\.codex\secrets\huada_ssh.txt`

This file is outside the repository and must never be committed to Git.

### How SSH Is Refreshed

The user prefers not to pre-run terminal commands manually.

Therefore the operating model is:

1. the user sends updated SSH information in the desktop conversation
2. desktop Codex writes or overwrites `C:\Users\lalala\.codex\secrets\huada_ssh.txt`
3. desktop Codex uses the Huada / Empyrean remote skill chain to connect and continue phase-2A work

### Expired Or Invalid SSH

If phase-2A starts and the SSH information is invalid, expired, or rejected:

- desktop Codex must stop backend execution immediately
- desktop Codex must report in the desktop conversation:
  - that SSH is invalid or expired
  - that fresh SSH information is required
- the user provides new SSH information in the desktop conversation
- desktop Codex overwrites `C:\Users\lalala\.codex\secrets\huada_ssh.txt`
- desktop Codex retries phase-2A execution

The user should not need to open a terminal to recover from this state.

---

## Local Phase-2A Package

### Windows Master Copy

Each phase-2A run must produce a reproducible local package stored under:

- `C:\Users\lalala\.codex\backend_runs\`

Recommended directory shape:

- `C:\Users\lalala\.codex\backend_runs\<request_id>\<backend_run_id>\`

### Required Contents

Each local phase-2A package must contain enough material to reproduce or audit the synthesis / Formal EC baseline after the remote server resets.

Required contents:

- run summary
- synthesis log
- mapped netlist
- synthesis power report
- synthesis area report
- synthesis timing summary report
- proof that constraints loaded correctly
- Formal EC log
- Formal EC summary report
- the exact backend scripts actually executed for this run
- the exact input files actually used for this run, unless they are already safely pinned by repository commit and path
- an execution manifest covering:
  - request id
  - PR number
  - commit
  - tag
  - backend run id
  - timestamp
  - remote host identity
  - command list
  - tool / environment summary

### What Must Be Copied Versus Only Referenced

If a backend script or input file was:

- generated on the server
- modified on the server
- not stably versioned in Git
- otherwise not guaranteed to be reconstructable later

then it must be copied into the local package.

If a backend script or input file is already:

- tracked in Git
- pinned by commit
- recoverable by repository path and commit id

then the local package may record a precise reference instead of copying a duplicate.

### What Must Not Be Pulled Back

The system should not attempt to archive entire remote tool installations or large stable infrastructure payloads such as:

- PDK trees
- standard cell libraries
- full tool install directories
- unrelated remote cache directories

Phase-2A is about reproducibility of the run, not cloning the entire server.

---

## GitHub Result Model

### Same Request PR

Phase-2A results must continue to attach to the **same request PR** that already carried phase-1.

The user should be able to inspect one PR and see the complete chain:

- request
- plan
- frontend execution
- frontend review
- synthesis / Formal EC baseline execution
- baseline review

### Slim GitHub Payload

Windows keeps the master local package.

GitHub stores a slim baseline result set sufficient for GPT-5.4 review and human traceability.

Recommended repository structure:

- `docs/runs/<request_id>/backend/<backend_run_id>/summary.md`
- `docs/runs/<request_id>/backend/<backend_run_id>/manifest.json`
- `docs/runs/<request_id>/backend/<backend_run_id>/reports/synthesis_area.rpt`
- `docs/runs/<request_id>/backend/<backend_run_id>/reports/synthesis_power.rpt`
- `docs/runs/<request_id>/backend/<backend_run_id>/reports/synthesis_timing_summary.rpt`
- `docs/runs/<request_id>/backend/<backend_run_id>/reports/formal_ec_summary.md`

The mapped netlist and full logs must exist in the Windows master package even if they are not all committed into GitHub.

### PR Comment Surface

Phase-2A should introduce a dedicated PR comment marker:

- `<!-- wf:backend-run -->`

This comment should summarize:

- backend run id
- commit
- tag
- local master package id
- GitHub slim artifact path
- synthesis status
- mapped netlist status
- constraint-load status
- Formal EC status
- synthesis power / area / timing summary headline

GPT-5.4 should publish a backend review comment marked with:

- `<!-- wf:backend-review -->`

Phase-2A does **not** require a `wf:backend-plan` surface because there is no automatic backend optimization loop in this phase.

---

## Versioning And Tagging

Every phase-2A round must map to an unambiguous Git tag.

Recommended tag families:

- `v0.1_phase2a_pass_YYYYMMDD_HHMMSS_rNNN`
- `v0.1_phase2a_fail_YYYYMMDD_HHMMSS_rNNN`

These tags remain ASCII-only and script-friendly, while still exposing:

- version
- stage / outcome
- timestamp
- iteration identity

The user does not manage this naming manually. Desktop Codex does.

---

## Phase-2A State Model

Phase-2A extends the PR-driven model with the minimal backend states needed after `wf:frontend-passed`.

As in phase-1, only one primary workflow label may exist on a PR at a time.

Recommended phase-2A states:

- `wf:backend-queued`
- `wf:backend-running`
- `wf:awaiting-backend-review`
- `wf:backend-blocked`
- `wf:backend-passed`
- `wf:backend-failed`

Meaning:

- `wf:backend-queued`
  - user has approved phase-2A start and the PR is waiting for local execution

- `wf:backend-running`
  - desktop Codex currently owns the synthesis / Formal EC run

- `wf:awaiting-backend-review`
  - baseline artifacts have been published and GPT-5.4 is reviewing them

- `wf:backend-blocked`
  - execution is waiting on refreshed SSH information or another recoverable prerequisite

- `wf:backend-passed`
  - the hard phase-2A gate passed

- `wf:backend-failed`
  - phase-2A failed and needs manual follow-up

### State Transition Rules

- the PR remains in `wf:frontend-passed` until the user replies `继续后端`
- a valid desktop `继续后端` transitions the PR to `wf:backend-queued`
- desktop Codex claim transitions `wf:backend-queued` to `wf:backend-running`
- successful artifact publication transitions `wf:backend-running` to `wf:awaiting-backend-review`
- GPT backend review with outcome `pass` transitions `wf:awaiting-backend-review` to `wf:backend-passed`
- GPT backend review with outcome `failed` transitions `wf:awaiting-backend-review` to `wf:backend-failed`
- missing or expired SSH transitions any pending execution state into `wf:backend-blocked`
- refreshed SSH and successful retry transitions `wf:backend-blocked` back to `wf:backend-running` or `wf:backend-queued`, depending on how the retry is implemented

Phase-2A terminal states are:

- `wf:backend-passed`
- `wf:backend-failed`

Only after one of these states is reached should the user decide whether to continue toward phase-2B, revise RTL first, or otherwise stop.

---

## Phase-2A Review Outcomes

GPT-5.4 phase-2A review must produce exactly one of these outcomes:

- `pass`
- `failed`

Meaning:

- `pass`
  - logic synthesis succeeded
  - mapped netlist generation succeeded
  - synthesis constraints loaded normally
  - Formal EC passed
  - required baseline artifacts were collected

- `failed`
  - one or more hard phase-2A gate conditions did not hold, or the baseline artifact set is not trustworthy

The review may still include warnings about bad synthesis-stage power / area / timing, but those warnings do **not** convert phase-2A into an automatic optimization loop.

---

## Pass Criteria

Phase-2A passes only if all of the following are true:

1. logic synthesis succeeds
2. mapped netlist generation succeeds
3. synthesis constraints load normally
4. Formal EC passes
5. the required logs / reports / manifest / baseline artifacts are collected

### Baseline Reports Are Required But Not Optimized Here

The following must be collected and summarized:

- synthesis power
- synthesis area
- synthesis timing summary

These values are required because:

- synthesis power is itself relevant to the contest scoring
- synthesis area and synthesis timing are useful early warning signals
- later phases need a baseline to compare against

But phase-2A does **not** run a multi-round optimization loop around these values.

If the collected baseline looks obviously catastrophic, desktop Codex may stop before phase-2B and ask whether RTL should be revised first.

---

## Success Criteria

Phase-2A is successful when one request can complete this path:

1. phase-1 reaches `wf:frontend-passed`
2. desktop Codex reports back in the desktop conversation
3. user replies `继续后端`
4. desktop Codex reads the local SSH secret, connects to the Huada server, and runs logic synthesis plus Formal EC
5. desktop Codex saves a reproducible Windows master package under `C:\Users\lalala\.codex\backend_runs\...`
6. desktop Codex publishes a slim baseline result set back to the same request PR
7. GPT-5.4 reviews the baseline package and returns `pass` or `failed`

---

## Out Of Scope

Phase-2A intentionally does not yet define:

- place and route commands
- STA across the final required corners
- automatic PPA optimization loops
- LVS
- SPEF extraction
- physical verification
- phase-2B or phase-2C signoff criteria
- fully automatic competition submission packaging

Those belong in later design documents.
