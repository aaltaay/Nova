@echo off
setlocal
cd /d "%~dp0"

echo Stopping Nova (API on :8000, UI on :5173)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-NovaPorts.ps1" -Ports "8000,5173"
echo.
echo Done. If any "Nova - API" / "Nova - UI" windows are still open, they can now be closed.
pause
