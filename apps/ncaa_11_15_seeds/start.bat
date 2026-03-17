@echo off
setlocal

:: ============================================================
:: NCAA 11-15 Seeds — Start
:: Serves from workspace root so ../../_shared/ paths resolve.
:: ============================================================

cd /d "%~dp0..\.."

echo Starting local server for NCAA 11-15 Seeds...
start "NCAA 11-15 Seeds Server" python -m http.server 8080
timeout /t 2 /nobreak >nul
start "" http://ncaa.localhost:8080/apps/ncaa_11_15_seeds/
exit /b 0
