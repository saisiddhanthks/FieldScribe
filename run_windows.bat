@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r backend\requirements.txt
  pip install -r backend\requirements-asr.txt
  pip install -r backend\requirements-hub.txt
) else (
  call .venv\Scripts\activate.bat
)
if not exist backend\.env copy backend\.env.example backend\.env >nul
python run.py
pause
