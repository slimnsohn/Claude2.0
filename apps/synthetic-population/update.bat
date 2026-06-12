@echo off
cd /d "%~dp0"
echo Running population update cycle...
python run_update_cycle.py
if errorlevel 1 (
    echo Update cycle FAILED.
    pause
    exit /b 1
)
echo Done.
