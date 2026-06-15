@echo off
REM One-click nightly refresh: pull the current NBA season's new games.
cd /d "%~dp0"
python ingest.py update
echo.
pause
