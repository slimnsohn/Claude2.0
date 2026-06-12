@echo off
cd /d "%~dp0"
set PATH=C:\Users\slims\miniconda3;C:\Users\slims\miniconda3\Scripts;%PATH%

echo Installing dependencies...
pip install -r requirements.txt -q

echo Starting server on http://localhost:5000
timeout /t 2 /nobreak >nul & start http://localhost:5000
python server.py

echo.
echo Server stopped. Press any key to close.
pause >nul
