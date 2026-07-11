@echo off
cd /d "%~dp0"
set "NOVA_API_PORT=8012"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\Start-NovaApi.ps1" -LogFile "logs\_test_launch.log"
