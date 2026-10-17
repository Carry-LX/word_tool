@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "REPORT_DEMO_OPEN_BROWSER=1"
"E:\conda_envs\graph-rag\python.exe" -B scripts\run_demo_dashboard.py
if errorlevel 1 pause
