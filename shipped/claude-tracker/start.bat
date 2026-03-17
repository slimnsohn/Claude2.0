@echo off
cd /d "%~dp0"

:: Install dependencies if needed
if not exist node_modules (
    echo Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

:: Launch Electron detached (no terminal window stays open)
start "" /B npx electron .
exit
