@echo off
rem ResMap daily refresh (for Task Scheduler). Keeps the living dataset current:
rem   1. ingest  — pull markets from all venues + detect rule changes (idempotent)
rem   2. export  — refresh the Parquet analytical snapshot
rem
rem Deliberately does NOT run parse / equivalence — those use `claude -p` and the
rem human review is the moat, so they stay manual. Run them yourself in batches:
rem   python -m parse.rule_parser --limit 20  &&  python -m parse.review_cli list
rem
rem Register (daily 06:00):
rem   schtasks /Create /TN "ResMap Daily Refresh" /TR "%~f0" /SC DAILY /ST 06:00 /F
cd /d "%~dp0.."
if not exist logs mkdir logs

echo [%date% %time%] refresh start >> logs\daily_refresh.log
call .venv\Scripts\python.exe -m ingest.run            >> logs\daily_refresh.log 2>&1
call .venv\Scripts\python.exe -m export.to_parquet --out export\parquet >> logs\daily_refresh.log 2>&1
echo [%date% %time%] refresh done  >> logs\daily_refresh.log
