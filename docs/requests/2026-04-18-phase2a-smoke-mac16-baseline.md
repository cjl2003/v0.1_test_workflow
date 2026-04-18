# Frontend Request: phase2a-smoke-mac16-baseline

- Request Id: `req-20260418-101500-phase2a-smoke-mac16-baseline`
- Title: `phase2a-smoke-mac16-baseline`
- Stage: `phase-1`
- Base Branch: `main`
- Work Branch: `request/2026-04-18-phase2a-smoke-mac16-baseline`
- Version: `r001`

## Goal
基于当前 `main` 上的 MAC16 基线，执行一次最小 frontend handoff request：先完成 phase-1 范围内的审查、必要时的最小前端修正，以及固定前端验证；目标是让同一条 request PR 停在 `wf:frontend-passed`，作为后续 phase-2A backend smoke 的接力起点。若当前基线已经足以通过 phase-1，则不要求额外功能性修改。

## In-Scope Items
- 对照 `docs/spec.md`、`docs/golden_vectors.md` 与当前 `rtl/mac16.sv`、`tb/tb_mac16.sv` 做 phase-1 范围内的前端确认。
- 若存在阻塞 `wf:frontend-passed` 的前端问题，只做最小、安全、可解释的 frontend 修正。
- 保持同一条 request PR 在 `wf:frontend-passed` 后继续保持 open，供桌面 Codex 后续手动触发 `/continue-backend`。

## Out-of-Scope Items
- 在 `wf:frontend-passed` 之前启动任何 backend 行为。
- P&R、STA、LVS、SPEF、功耗/面积优化循环或任何 phase-2B / phase-2C 内容。
- `wf:frontend-passed` 后自动合并 PR。
- 自动 replan、自动 rerun、自动 continue-backend。

## Acceptance Criteria
- GitHub 发布 `wf:clarification` 或 `wf:plan`。
- 若计划获批，本地 phase-1 执行通过 `sim/run_iverilog.bat`。
- 若计划获批，本地 phase-1 执行通过 `python tools/check_golden.py`。
- 最新 GPT frontend review 将同一条 request PR 推进到 `wf:frontend-passed` 或 `wf:rework-needed`。
- 若达到 `wf:frontend-passed`，该 PR 继续保持 open，等待桌面对话中的显式 `继续后端` 再进入 phase-2A。

## Operating Constraints
- 在达到 `wf:frontend-passed` 之前，严格遵守 `docs/superpowers/specs/2026-04-17-pr-driven-rtl-frontend-autoflow-design.md`。
- planner 和 frontend review 都不得擅自扩展到 backend 执行内容。
- 到达 `wf:frontend-passed` 后，桌面 Codex 只做状态汇报，不自动合并，不自动启动 backend。
- phase-2A 只在用户桌面对话明确回复 `继续后端` 后，由桌面 Codex 代发 `/continue-backend` 并继续执行。
