@echo off
title Uninstall FieldScribe
rem run from a temp copy so this file can delete its own folder
if /I not "%~dp0"=="%TEMP%\" (
  copy /Y "%~f0" "%TEMP%\%~nx0" >nul
  "%TEMP%\%~nx0"
  exit /b
)
set "APP=%LOCALAPPDATA%\Programs\FieldScribe"
set "BACKUP=%USERPROFILE%\Documents\FieldScribe backup"
echo.
echo   This removes FieldScribe from this laptop.
echo   Patient records and the encryption key are first copied to:
echo     %BACKUP%
echo   (Ollama and its models stay installed; remove them from Windows Settings ^> Apps if you want.)
echo.
choice /C YN /M "  Continue"
if errorlevel 2 exit /b 0
taskkill /F /FI "WINDOWTITLE eq FieldScribe*" >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Programs\FieldScribe*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
if exist "%APP%\backend\data" robocopy "%APP%\backend\data" "%BACKUP%\data" /E /NFL /NDL /NJH /NJS >nul
if exist "%APP%\backend\.env" copy /Y "%APP%\backend\.env" "%BACKUP%\.env" >nul
del "%USERPROFILE%\Desktop\FieldScribe.lnk" >nul 2>&1
rmdir /S /Q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\FieldScribe" >nul 2>&1
cd /d "%TEMP%"
rmdir /S /Q "%APP%"
echo.
echo   FieldScribe removed. Your records are in "%BACKUP%".
pause
