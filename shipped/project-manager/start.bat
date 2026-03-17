@echo off

:: ============================================================
:: Project Manager — Start
:: ============================================================

cd /d "%~dp0"

if not exist "venv\" (
    echo Creating virtual environment...
    %USERPROFILE%\miniconda3\python.exe -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo Starting Project Manager on http://project-manager.localhost:5050
start "" http://project-manager.localhost:5050
python server.py
pause
