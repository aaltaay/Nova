@echo off
setlocal
cd /d "%~dp0"

echo Preparing Nova Desktop (closing any previous instance on ports 8000 / 5173)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-NovaPorts.ps1" -Ports "8000,5173" >nul 2>&1
timeout /t 1 /nobreak >nul

echo Starting Nova desktop (Electron + local API)...
echo Logs: backend\logs\blast.log  (Electron safely stops the API sidecar on quit)
echo.
cd frontend
call npm run electron:dev
