@echo off
REM Opens the SimCore22 web UI (player app, live leaderboard, admin portal) on your real data.
REM The engine (run_bay.bat) records rounds; this only shows them, so it can run on its own.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Run setup_bay.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m simcore22.web --open
pause
