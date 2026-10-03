@echo off
REM Starts SimCore22 on a bay PC:
REM   1. the web UI (live leaderboard + admin portal), in its own minimized window
REM   2. the engine (reads GSPro, scores rounds), in this window
REM In this window type  end  to finish a round early,  save  to checkpoint,  help  for more.
REM Ctrl+C stops the engine and saves any round in progress.
REM Run setup_bay.bat first, once per PC.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Run setup_bay.bat first.
    pause
    exit /b 1
)

start "SimCore22 web UI" /min ".venv\Scripts\python.exe" -m simcore22.web --open

".venv\Scripts\python.exe" -m simcore22.engine.engine_loop
pause
