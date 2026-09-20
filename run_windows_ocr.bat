@echo off
cd C:\SimCore22_MVP
call venv\Scripts\activate
python -m mvp.engine.ocr.bootstrap_windows
pause
