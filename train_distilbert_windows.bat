@echo off
cd /d "%~dp0"
if not exist .venv ( echo Run run_windows.bat once first. & pause & exit /b 1 )
call .venv\Scripts\activate.bat
pip install -r backend\requirements-ml.txt
cd backend
python train_ner.py
echo.
echo Done. Restart FieldScribe (run_windows.bat) to use the hybrid engine.
pause
