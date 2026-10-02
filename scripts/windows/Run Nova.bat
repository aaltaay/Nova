@echo off
setlocal
rem This launcher lives in scripts\windows; Nova's folder is two levels up.
for %%I in ("%~dp0..\..") do set "NOVA=%%~fI"
cd /d "%NOVA%"

if not exist "backend\logs" mkdir "backend\logs"

echo Preparing Nova (closing any previous instance on ports 8000 / 5173)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%NOVA%\scripts\Stop-NovaPorts.ps1" -Ports "8000,5173" >nul 2>&1
timeout /t 1 /nobreak >nul

echo Starting Nova (API + UI)...
echo.
echo   API:  http://127.0.0.1:8000
echo   App:  http://localhost:5173  (browser opens shortly)
echo   Logs: backend\logs\api-console.log  /  backend\logs\ui-console.log
echo.
echo Close each titled window OR run "scripts\windows\Stop Nova.bat" to shut Nova down cleanly.
echo.

start "Nova — API" /D "%NOVA%\backend" powershell -NoProfile -ExecutionPolicy Bypass -File "%NOVA%\scripts\Start-NovaApi.ps1"
timeout /t 2 /nobreak >nul
start "Nova — UI" /D "%NOVA%\frontend" powershell -NoProfile -ExecutionPolicy Bypass -File "%NOVA%\scripts\Start-NovaUi.ps1"
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"
