@echo off
setlocal
cd /d "%~dp0"

echo Stopping Nova (API on :8000, UI on :5173, brain client)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-NovaPorts.ps1" -Ports "8000,5173"
taskkill /FI "WINDOWTITLE eq Nova -- Brain*" /T /F >nul 2>&1
echo.
echo Done. If any "Nova - API" / "Nova - UI" / "Nova - Brain" windows are still open, they can now be closed.
pause
