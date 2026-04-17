# MAC16 Phase-1 Frontend Workflow

本仓库用于实现并验证集创赛 MAC16 题目的前端内容，同时承载一个基于 PR 的 phase-1 RTL frontend 自动化流程。当前范围只覆盖前端需求整理、计划审批、本地 RTL/testbench 修改，以及固定的前端校验，不包含远端执行或后端实现。

## 项目内容

- `rtl/mac16.sv`：主设计文件，完成 16 bit 串行输入、24 bit 串行输出的 MAC16 逻辑
- `tb/tb_mac16.sv`：主自检 testbench，覆盖 `mode=0`、`mode=1` 和 mode 切换场景
- `docs/spec.md`：题目规格与 mode 切换澄清口径
- `docs/golden_vectors.md`：golden 输入、乘积、各模式预期输出与 carry 结果
- `sim/run_iverilog.bat`：phase-1 固定前端仿真入口
- `tools/check_golden.py`：golden 文档一致性与仿真日志检查脚本

## 目录说明

- `docs/`：规格、request 文档、run 结果和流程设计说明
- `rtl/`：RTL 源码，当前主目标为 `mac16.sv`
- `tb/`：SystemVerilog testbench
- `sim/`：本地仿真脚本与仿真说明
- `tools/`：request planning、command routing、frontend review、golden check 等 phase-1 自动化脚本
- `tests/`：Python 侧单元测试
- `.github/`：PR 驱动自动化相关的 GitHub workflow

## 快速使用

先根据本机环境准备 Python 与仿真工具。Python 依赖可通过下面命令安装：

```powershell
pip install -r requirements.txt
```

本仓库 phase-1 的固定前端校验入口如下：

```powershell
sim\run_iverilog.bat
python tools\check_golden.py
```

- `sim\run_iverilog.bat` 会编译并运行 `rtl/mac16.sv` 与 `tb/tb_mac16.sv`
- `python tools\check_golden.py` 会校验 `docs/golden_vectors.md`，并在存在 `sim/run_iverilog.log` 时检查日志中是否包含 `Simulation Passed`
- 仿真工具链路径和可选的 ModelSim 用法见 `sim/README.md`

如需运行 Python 侧回归测试，可执行：

```powershell
python -m unittest discover tests
```

## 文档索引

- 题目规格与切换语义：`docs/spec.md`
- Golden vectors：`docs/golden_vectors.md`
- 当前 phase-1 PR 驱动流程设计：`docs/superpowers/specs/2026-04-17-pr-driven-rtl-frontend-autoflow-design.md`
- 当前请求示例：`docs/requests/2026-04-17-readme-md.md`
- 仿真说明：`sim/README.md`

## 注意事项

- 本仓库当前只处理 phase-1 frontend workflow，不包含综合、STA、功耗、面积、形式验证、LVS 或 PnR
- `docs/runs/` 用于保存成功执行后的 run 摘要，属于流程产物目录
- 计划执行应以 PR 中最新的 `wf:plan` 为准，不应自动扩展到未批准范围
