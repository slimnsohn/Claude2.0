@echo off
cd /d "%~dp0..\.."
timeout /t 1 /nobreak >nul & start "" "http://localhost:8080/apps/tweet-text-grabber/"
echo Serving at http://localhost:8080/apps/tweet-text-grabber/
echo Press Ctrl+C to stop.
python -m http.server 8080
