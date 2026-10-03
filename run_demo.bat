@echo off
REM Shows the whole product with a fictional league - no bay, no GSPro needed.
REM Everything on screen is labelled DEMO and none of it touches your real data.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Run setup_bay.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m simcore22.web --demo --open
pause
