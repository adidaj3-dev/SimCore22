@echo off
REM Launches the SimCore22 engine (Foresight listener + OCR + leaderboard).
REM Run setup_bay.bat first, once per PC.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Run setup_bay.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m simcore22.engine.engine_loop
pause
