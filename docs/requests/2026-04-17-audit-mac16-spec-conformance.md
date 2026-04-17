# Frontend Request: audit-mac16-spec-conformance

- Request Id: `req-20260417-094733-audit-mac16-spec-conformance`
- Title: `audit-mac16-spec-conformance`
- Stage: `phase-1`
- Base Branch: `main`
- Work Branch: `request/2026-04-17-audit-mac16-spec-conformance`
- Version: `r001`

## Goal
对照 docs/spec.md 审查 rtl/mac16.sv 与 tb/tb_mac16.sv 是否符合比赛题目要求；若存在需求语义歧义，先提出澄清问题；本轮只做符合性审查，不自动修改 RTL、testbench 或其他仓库文件。

## In-Scope Items
- 对照 docs/spec.md 审查 rtl/mac16.sv 与 tb/tb_mac16.sv 是否符合比赛题目要求；若存在需求语义歧义，先提出澄清问题；本轮只做符合性审查，不自动修改 RTL、testbench 或其他仓库文件。
- Only the current phase-1 frontend workflow defined in the repository spec.

## Out-of-Scope Items
- Remote server execution.
- Backend optimization, synthesis, STA, power, area, formal, LVS, or PnR.
- Automatic replan or rerun behavior.

## Acceptance Criteria
- GitHub publishes either wf:clarification or wf:plan.
- Local execution, when approved, passes sim/run_iverilog.bat.
- Local execution, when approved, passes python tools/check_golden.py.
- Final GPT frontend review reaches wf:frontend-passed or wf:rework-needed.

## Operating Constraints
- Follow docs/superpowers/specs/2026-04-17-pr-driven-rtl-frontend-autoflow-design.md exactly.
- Do not extend beyond phase-1.
- Do not auto-replan or auto-rerun.
