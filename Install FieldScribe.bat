@echo off
title FieldScribe installer
echo.
set "ED=full"
if exist "%~dp0edition.txt" set /p ED=<"%~dp0edition.txt"
if /I "%ED%"=="lite" (
  echo   Installing FieldScribe Lite: essentials only, about 0.3 GB to download
  echo   ^(app, small Whisper speech model, map^). Takes about 5 minutes.
) else (
  echo   Installing FieldScribe Full. This downloads about 3-7 GB the first time
  echo   ^(best speech model, local AI model, map^) and can take 10-30 minutes.
)
echo   After that, FieldScribe works with no internet.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1" %*
if errorlevel 1 (
  echo.
  echo   Something went wrong. The full log is in %TEMP%\fieldscribe-install.log
  echo   Fix the problem shown above, then double-click this file again. It resumes where it stopped.
)
echo.
pause
