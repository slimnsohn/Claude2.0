@echo off
setlocal

:: ============================================================
:: Project Manager — Start
:: ============================================================

cd /d "%~dp0"

if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo Starting Project Manager on http://localhost:5050
start "" http://localhost:5050
python server.py
