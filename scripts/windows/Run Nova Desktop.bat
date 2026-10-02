@echo off
setlocal
rem This launcher lives in scripts\windows; Nova's folder is two levels up.
for %%I in ("%~dp0..\..") do set "NOVA=%%~fI"
cd /d "%NOVA%"

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%NOVA%\scripts\Ensure-NovaMaintenanceTask.ps1"
if errorlevel 1 echo WARNING: Repo maintenance setup failed; desktop startup continues.

echo Preparing Nova Desktop (closing any previous instance on ports 8000 / 5173)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%NOVA%\scripts\Stop-NovaPorts.ps1" -Ports "8000,5173" >nul 2>&1
timeout /t 1 /nobreak >nul

echo Starting Nova desktop (Electron + local API)...
echo Logs: backend\logs\blast.log  (Electron safely stops the API sidecar on quit)
echo.
cd frontend
call npm run electron:dev
