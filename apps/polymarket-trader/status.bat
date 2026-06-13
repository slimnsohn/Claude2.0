@echo off
REM polymarket-trader — is it alive? Double-click any time.
cd /d "%~dp0"
.venv\Scripts\python scripts\status.py
pause
