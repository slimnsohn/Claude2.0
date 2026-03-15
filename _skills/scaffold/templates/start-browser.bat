@echo off
setlocal

:: ============================================================
:: {PROJECT_NAME} — Start
:: Single entry point. Installs deps if needed, starts server, opens browser.
:: ============================================================

cd /d "%~dp0"

:: --- Node project ---
if exist "package.json" (
    if not exist "node_modules\" (
        echo Installing dependencies...
        call npm install
        if errorlevel 1 (
            echo [ERROR] npm install failed.
            pause
            exit /b 1
        )
    )
    echo Starting dev server...
    start "" cmd /c "npm run dev"
    timeout /t 3 /nobreak >nul
    
    :: Try to detect the port from package.json or default to 3000
    start "" http://localhost:3000
    exit /b 0
)

:: --- Python project ---
if exist "requirements.txt" (
    if not exist "venv\" (
        echo Creating virtual environment...
        python -m venv venv
        call venv\Scripts\activate.bat
        pip install -r requirements.txt
    ) else (
        call venv\Scripts\activate.bat
    )
    echo Starting server...
    start "" python -m http.server 8080
    timeout /t 2 /nobreak >nul
    start "" http://localhost:8080
    exit /b 0
)

:: --- Static HTML (no package.json, no requirements.txt) ---
if exist "index.html" (
    echo Starting local server for static files...
    start "" cmd /c "python -m http.server 8080"
    timeout /t 2 /nobreak >nul
    start "" http://localhost:8080
    exit /b 0
)

echo [ERROR] No recognized project type found.
echo Expected: package.json, requirements.txt, or index.html
pause
