@echo off
cd /d "%~dp0"

:: Activate Miniconda
call C:\Users\slims\miniconda3\Scripts\activate.bat
pip install -q -r requirements.txt

:: Open browser after short delay
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"

:: Start web server
python server.py
