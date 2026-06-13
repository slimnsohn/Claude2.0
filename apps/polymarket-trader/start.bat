@echo off
REM polymarket-trader — single entry point: deps + watchdog-supervised trader + dashboard
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)

start "" http://127.0.0.1:8765
.venv\Scripts\python watchdog.py
