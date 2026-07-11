@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\logs" mkdir "backend\logs"

echo Preparing Nova (closing any previous instance on ports 8000 / 5173)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-NovaPorts.ps1" -Ports "8000,5173" >nul 2>&1
timeout /t 1 /nobreak >nul

echo Starting Nova (API + UI)...
echo.
echo   API:  http://127.0.0.1:8000
echo   App:  http://localhost:5173  (browser opens shortly)
echo   Logs: backend\logs\api-console.log  /  backend\logs\ui-console.log
echo.
echo Close each titled window OR run "Stop Nova.bat" to shut Nova down cleanly.
echo.

start "Nova — API" /D "%~dp0backend" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-NovaApi.ps1"
timeout /t 2 /nobreak >nul
start "Nova — UI" /D "%~dp0frontend" powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-NovaUi.ps1"
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"
