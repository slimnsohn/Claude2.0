@echo off
REM Fantasy Basketball web UI — single entry point.
cd /d "%~dp0"
python -c "import flask" 2>nul || python -m pip install flask
start "" http://127.0.0.1:5050
python app.py
