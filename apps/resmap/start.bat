@echo off
rem ResMap single entry point: ensure deps, start the read-only API, open the
rem demo dashboard. The data pipeline (ingest/parse/equivalence) runs separately
rem via `python -m ...` — see README.md.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating venv + installing dependencies...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

rem API reads DATABASE_URL from .env (main.py calls load_dotenv)
start "ResMap API" cmd /k ".venv\Scripts\python.exe -m uvicorn tool.api.main:app --port 8077"
timeout /t 3 >nul
rem open the landing page — it links to the guide, FAQ, and live dashboard
start "" "%~dp0tool\web\index.html"
