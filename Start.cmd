@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" desktop.py
) else (
  echo Install the release EXE or follow README.md to set up the source environment.
  pause
)

