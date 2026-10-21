@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" goto ready
if exist "E:\conda_envs\graph-rag\python.exe" (
  "E:\conda_envs\graph-rag\python.exe" -m venv .venv
) else (
  py -3.12 -m venv .venv
)
if errorlevel 1 goto failed
:ready
".venv\Scripts\python.exe" tools\migration\setup_new_computer.py
if errorlevel 1 goto failed
echo Setup complete. Run start_report_demo.cmd.
pause
exit /b 0
:failed
echo Setup failed. See docs\MIGRATION.md for Python 3.12, GitHub CLI and Word prerequisites.
pause
exit /b 1
