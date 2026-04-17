@echo off
setlocal

:: ============================================================
:: House Room Tracker — Start
:: Single entry point. Starts local server, opens browser.
:: ============================================================

cd /d "%~dp0"

:: --- Static HTML ---
if exist "index.html" (
    echo Starting local server for static files...
    start "House Room Tracker Server" python -m http.server 8080
    timeout /t 2 /nobreak >nul
    start "" http://house-room-tracker.localhost:8080
    exit /b 0
)

echo [ERROR] No index.html found.
pause
