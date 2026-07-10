@echo off
cd /d "%~dp0frontend"
echo Starting Nova desktop (Electron + local API)...
echo.
call npm run electron:dev
