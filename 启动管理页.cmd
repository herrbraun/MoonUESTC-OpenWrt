@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run the installer first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 desktop.py
if errorlevel 1 pause
