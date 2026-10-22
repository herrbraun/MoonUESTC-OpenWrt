@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto ready
where py >nul 2>nul
if errorlevel 1 (python -m venv .venv) else (py -3 -m venv .venv)
if errorlevel 1 goto failed
:ready
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 lite.py selftest
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -X utf8 tools\install_windows.py
if errorlevel 1 goto failed
echo Installation complete. Open the dashboard launcher.
pause
exit /b 0
:failed
echo Installation failed. Python 3.10 or newer and Windows Task Scheduler are required.
pause
exit /b 1
