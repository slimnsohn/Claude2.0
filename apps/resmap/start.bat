@echo off
rem ResMap single entry point: ensure deps, start the read-only product API + the
rem local control server, then open the landing page. From the website you can then
rem browse the data (Dashboard) and trigger a refresh (Control) — no terminal needed.
rem Heavy/curated steps (parse, equivalence) still run via `python -m ...` — see README.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating venv + installing dependencies...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

rem both servers read DATABASE_URL from .env (load_dotenv)
start "ResMap API"     cmd /k ".venv\Scripts\python.exe -m uvicorn tool.api.main:app --port 8077"
start "ResMap Control" cmd /k ".venv\Scripts\python.exe -m uvicorn tool.api.control:app --host 127.0.0.1 --port 8078"
timeout /t 3 >nul
rem landing page links to the guide, FAQ, live dashboard, and control panel
start "" "%~dp0tool\web\index.html"
