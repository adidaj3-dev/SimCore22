@echo off
cd C:\
git clone https://github.com/SimCore22/SimCore22_MVP.git
cd SimCore22_MVP
python -m venv venv
call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
@echo off Enviornment Ready
pause
