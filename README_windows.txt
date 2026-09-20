SIMCORE22 - WINDOWS OCR-ONLY MVP
================================

This folder contains ONLY the Windows-specific pieces needed to run
the OCR-only MVP on the commercial bay.

FILES
-----

windows_requirements.txt
    Extra Python dependencies for Windows:
    - mss
    - pytesseract
    - opencv-python
    - numpy

ocr/capture_windows.py
    Windows-only monitor capture using MSS.
    Captures the full GSPro HUD monitor as a BGR numpy array.

ocr/bootstrap_windows.py
    Windows-only bootstrapper.
    - Starts round (RoundStartOCR)
    - Starts EventDispatcher
    - Starts Windows capture loop
    - Feeds frames into OCRHudListener

run_windows_ocr.bat
    Convenience launcher for the bay.
    - Activates venv
    - Runs: python -m mvp.engine.ocr.bootstrap_windows


SETUP STEPS ON WINDOWS BAY
--------------------------

1) Copy the entire SimCore22_MVP project to the bay machine.

2) Create and activate a virtual environment (if not already done):

    python -m venv venv
    venv\Scripts\activate

3) Install main project requirements (if you have a requirements.txt):

    pip install -r requirements.txt

4) Install Windows-specific requirements:

    pip install -r windows\\windows_requirements.txt

5) Install Tesseract for Windows:
    - Download the Windows installer (UB Mannheim build is recommended)
    - Install it
    - Ensure "tesseract.exe" is on PATH
      (you can verify by running "tesseract -v" in a new terminal)

6) Copy Windows OCR files into place:

    From USB:
        windows\\ocr\\capture_windows.py
        windows\\ocr\\bootstrap_windows.py

    To project:
        mvp\\engine\\ocr\\capture_windows.py
        mvp\\engine\\ocr\\bootstrap_windows.py

7) Launch OCR-only mode:

    - From project root:
        run_windows_ocr.bat

    or manually:

        venv\Scripts\activate
        python -m mvp.engine.ocr.bootstrap_windows

8) Open GSPro on the bay monitor.
   - Ensure the HUD is visible and stable.
   - Adjust monitor_index in bootstrap_windows.py if GSPro is not on monitor 1.

9) Hit a shot.
   - You should see PlayerEvent, HoleEvent, ShotEvent, etc. in the console.


NOTES
-----

- The Mac codebase remains unchanged.
- Windows uses capture_windows.py for monitor capture.
- OCRHudListener, RoundStartOCR, EventDispatcher, and the event model
  are shared between Mac and Windows.
- If OCR is noisy on the bay, you can still demo the event flow and
  architecture even with imperfect numbers.
