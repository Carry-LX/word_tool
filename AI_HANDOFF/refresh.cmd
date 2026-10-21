@echo off
setlocal
set "PYTHON_EXE=E:\conda_envs\graph-rag\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Python was not found. Edit PYTHON_EXE at the top of this file.
  pause
  exit /b 1
)
"%PYTHON_EXE%" -X utf8 -B "%~dp0tools\refresh_handoff.py"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo Refresh failed. Read the error above. Existing handoff files were preserved.
) else (
  echo Refreshed. Start with START_HERE.md. Update HANDOFF.md manually after each milestone.
)
pause
exit /b %RESULT%
