@echo off
setlocal

:: ============================================================
:: nautilus — Electron Start
:: Called by launch.vbs (headless) or directly from terminal.
:: ============================================================

cd /d "%~dp0"

:: Install deps if first run
if not exist "node_modules\" (
    echo Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. >> "%~dp0\launch-error.log"
        exit /b 1
    )
)

:: Launch Electron
call npx electron .
