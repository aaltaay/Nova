@echo off
cd /d "%~dp0"

REM Prefer Windows Python launcher; fall back to python on PATH
set "UV=py -3 -m uvicorn main:app --reload --reload-exclude logs --reload-exclude .cache --host 127.0.0.1 --port 8000"
where py >nul 2>&1 || set "UV=python -m uvicorn main:app --reload --reload-exclude logs --reload-exclude .cache --host 127.0.0.1 --port 8000"

echo Starting Stock Alert (API + UI)...
echo.
echo   API:  http://127.0.0.1:8000
echo   App:  http://localhost:5173  (browser opens shortly)
echo.
echo Close each titled window to stop that server.
echo.

start "Stock Alert — API" /D "%~dp0backend" cmd /k "%UV%"
timeout /t 2 /nobreak >nul
start "Stock Alert — UI" /D "%~dp0frontend" cmd /k npm run dev
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173"
