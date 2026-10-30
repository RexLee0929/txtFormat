@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    call setup.cmd
)
start "" ".venv\Scripts\pythonw.exe" "run.py"
endlocal
