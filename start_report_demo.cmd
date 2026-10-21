@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "REPORT_DEMO_OPEN_BROWSER=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -B scripts\run_demo_dashboard.py
) else if exist "E:\conda_envs\graph-rag\python.exe" (
  "E:\conda_envs\graph-rag\python.exe" -B scripts\run_demo_dashboard.py
) else (
  echo Run setup_new_computer.cmd first.
  pause
  exit /b 1
)
if errorlevel 1 pause
