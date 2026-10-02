@echo off
setlocal
rem This launcher lives in scripts\windows; Nova's folder is two levels up.
for %%I in ("%~dp0..\..") do set "NOVA=%%~fI"
cd /d "%NOVA%"

echo Stopping Nova (API on :8000, UI on :5173, brain client)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%NOVA%\scripts\Stop-NovaPorts.ps1" -Ports "8000,5173"
taskkill /FI "WINDOWTITLE eq Nova -- Brain*" /T /F >nul 2>&1
echo.
echo Done. If any "Nova - API" / "Nova - UI" / "Nova - Brain" windows are still open, they can now be closed.
pause
