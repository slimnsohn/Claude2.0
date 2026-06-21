@echo off
setlocal
cd /d "%~dp0"

REM --- Find a usable Python (a double-clicked .bat may not have conda on PATH) ---
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE if exist "%USERPROFILE%\miniconda3\python.exe" set "PYEXE=%USERPROFILE%\miniconda3\python.exe"
if not defined PYEXE if exist "%USERPROFILE%\anaconda3\python.exe"  set "PYEXE=%USERPROFILE%\anaconda3\python.exe"
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYEXE (
  echo [ERROR] Could not find Python. Install Python, or run this from an Anaconda Prompt.
  pause
  exit /b 1
)
echo Using Python: %PYEXE%

REM --- Make sure Flask is installed ---
"%PYEXE%" -c "import flask" 2>nul || "%PYEXE%" -m pip install flask

REM --- Open the browser a few seconds after the server has started ---
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:5050"

echo.
echo Fantasy Basketball running at http://127.0.0.1:5050
echo (Keep this window open. Close it to stop the server.)
echo.
"%PYEXE%" app.py
pause
