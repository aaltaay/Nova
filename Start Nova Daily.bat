@echo off
setlocal
cd /d "%~dp0"
echo Starting Nova daily bootstrap (Gateway + API + UI)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-NovaDaily.ps1"
if errorlevel 1 (
  echo.
  echo Daily start reported an error. See backend\logs\daily-start.log
  pause
)
