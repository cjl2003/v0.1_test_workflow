# 仿真运行说明

## 1. 准备条件

本工程默认使用下面两个工具链：

- Icarus Verilog
  - `E:\Verilog\iverilog_setup_pack\iverilog\bin\iverilog.exe`
  - `E:\Verilog\iverilog_setup_pack\iverilog\bin\vvp.exe`
- ModelSim
  - `E:\Verilog\ModelSim\setup_pack\win64\vlog.exe`
  - `E:\Verilog\ModelSim\setup_pack\win64\vsim.exe`

建议先进入工程根目录：

```powershell
cd /d E:\2026_JC_Competition\Project\mac16_4_15
```

## 2. Icarus 正常运行

直接运行下面的命令：

```powershell
.\sim\run_iverilog.bat
```

这个脚本会自动完成两步：

1. 编译 `rtl/mac16.sv` 和 `tb/tb_mac16.sv`
2. 运行生成的 `sim/mac16_tb.vvp`

正常情况下，仿真结束时控制台应看到：

```text
Simulation Passed
```

如果检查失败，则会看到：

```text
Simulation Failed
```

## 3. ModelSim 运行

在工程根目录运行下面的命令：

```powershell
E:\Verilog\ModelSim\setup_pack\win64\vsim.exe -c -do sim/run_modelsim.do
```

这个 `.do` 脚本会自动完成下面的动作：

1. 在 `sim/modelsim_work` 下创建并映射 `work` 库
2. 编译 `rtl/mac16.sv` 和 `tb/tb_mac16.sv`
3. 运行 `tb_mac16`
4. `run -all` 后自动退出

正常情况下，命令行输出中应包含：

```text
Simulation Passed
```

## 4. 可选 VCD 波形导出

如果想导出 Icarus 用的 VCD 波形，可以运行：

```powershell
.\sim\run_iverilog.bat vcd
```

这个模式会在编译时打开 `TB_ENABLE_VCD` 宏，并生成：

```text
sim/mac16_tb.vcd
```

说明：

- 这个 VCD 开关默认关闭，不会影响正常自检行为。
- 开启 VCD 后，Icarus 可能额外打印 VCD 相关提示信息，这不代表功能失败。
- 功能是否通过，仍然以 `Simulation Passed` 或 `Simulation Failed` 为准。

## 5. 产物说明

运行后常见产物如下：

- `sim/mac16_tb.vvp`：Icarus 编译后的可执行仿真文件
- `sim/mac16_tb.vcd`：可选的 Icarus 波形文件
- `sim/modelsim_work/`：ModelSim 的工作库目录
