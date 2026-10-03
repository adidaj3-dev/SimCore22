@echo off
REM ============================================================
REM  SimCore22 - one-page setup for a bay PC (run once per PC)
REM
REM  What it does:
REM    1. Installs Python 3.14 and Tesseract OCR if missing (winget)
REM    2. Creates a Windows virtual environment: .venv
REM    3. Installs this project's Python dependencies into it
REM    4. Runs the bay diagnostic so you know it worked
REM
REM  Run it by double-clicking, or from a terminal:
REM      setup_bay.bat
REM ============================================================
setlocal

cd /d "%~dp0"
echo.
echo === SimCore22 bay setup ===
echo Project folder: %cd%
echo.

where winget >nul 2>nul
if errorlevel 1 (
    echo ERROR: winget is not available on this PC.
    echo Install "App Installer" from the Microsoft Store, then re-run this script.
    pause
    exit /b 1
)

echo [1/4] Checking Python 3.14 ...
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not exist "%PYEXE%" (
    echo       Not found - installing Python 3.14 ...
    winget install --id Python.Python.3.14 -e --source winget --accept-package-agreements --accept-source-agreements
) else (
    echo       Already installed.
)
if not exist "%PYEXE%" (
    echo ERROR: Python install did not land where expected: %PYEXE%
    echo Open a NEW terminal window ^(so PATH refreshes^) and re-run this script.
    pause
    exit /b 1
)

echo.
echo [2/4] Checking Tesseract OCR ...
if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo       Not found - installing Tesseract OCR ...
    winget install --id tesseract-ocr.tesseract -e --source winget --accept-package-agreements --accept-source-agreements
) else (
    echo       Already installed.
)

echo.
echo [3/4] Creating virtual environment (.venv) and installing requirements ...
if not exist ".venv\Scripts\python.exe" (
    "%PYEXE%" -m venv .venv
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Scroll up for the real error.
    pause
    exit /b 1
)

echo.
echo [4/4] Running the bay diagnostic ...
echo       Bring GSPro / FSX to the front now if it's open.
".venv\Scripts\python.exe" -m simcore22.tools.bay_check

echo.
echo === Setup finished ===
echo To run SimCore22 later:  run_bay.bat
echo A captures\ folder with screenshots + report.json was just created.
echo Zip it and send it back if anything in the diagnostic looked wrong.
echo.
pause
