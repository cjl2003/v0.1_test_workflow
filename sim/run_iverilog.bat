@echo off
setlocal

set "IVERILOG=E:\Verilog\iverilog_setup_pack\iverilog\bin\iverilog.exe"
set "VVP=E:\Verilog\iverilog_setup_pack\iverilog\bin\vvp.exe"

for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
set "OUT_FILE=%ROOT_DIR%\sim\mac16_tb.vvp"
set "VCD_FILE=%ROOT_DIR%\sim\mac16_tb.vcd"
set "RTL_FILE=%ROOT_DIR%\rtl\mac16.sv"
set "TB_FILE=%ROOT_DIR%\tb\tb_mac16.sv"
set "DEFINES="

if /I "%~1"=="vcd" (
    set "DEFINES=-DTB_ENABLE_VCD"
    if exist "%VCD_FILE%" del /f /q "%VCD_FILE%"
)

pushd "%ROOT_DIR%"

"%IVERILOG%" -g2012 %DEFINES% -o "%OUT_FILE%" "%RTL_FILE%" "%TB_FILE%"
if errorlevel 1 goto :fail

"%VVP%" "%OUT_FILE%"
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

:fail
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
