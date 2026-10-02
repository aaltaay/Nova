@echo off
setlocal
rem This launcher lives in scripts\windows; Nova's folder is two levels up.
for %%I in ("%~dp0..\..") do set "NOVA=%%~fI"
cd /d "%NOVA%"
echo Starting Nova daily bootstrap (Gateway + API + UI)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%NOVA%\scripts\Start-NovaDaily.ps1"
if errorlevel 1 (
  echo.
  echo Daily start reported an error. See backend\logs\daily-start.log
  pause
)
