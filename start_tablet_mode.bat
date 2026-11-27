@echo off
rem Phones and tablets on the same Wi-Fi or this laptop's hotspot use FieldScribe running on this laptop.
rem HTTP :8000 for this laptop and the phone set-up page, HTTPS :8443 (the laptop's own certificate) for phones,
rem so they can dictate and add FieldScribe to the home screen. Everyone signs in with their own PIN.
cd /d "%~dp0"
if not exist .venv (
  echo Run run_windows.bat once first to set things up.
  pause & exit /b 1
)
call .venv\Scripts\activate.bat
set HOST=0.0.0.0
python run.py
pause
