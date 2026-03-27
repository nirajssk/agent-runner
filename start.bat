@echo off
setlocal

set ROOT=%~dp0

echo Starting Claude Agent Runner...

REM --- Backend ---
if not exist "%ROOT%backend\.venv" (
    echo [backend] Creating virtual environment...
    python -m venv "%ROOT%backend\.venv"
)

echo [backend] Installing dependencies...
call "%ROOT%backend\.venv\Scripts\activate.bat"
pip install -r "%ROOT%backend\requirements.txt" -q

echo [backend] Starting server on http://localhost:8000
start "Agent Runner - Backend" cmd /k "cd /d "%ROOT%backend" && call .venv\Scripts\activate.bat && uvicorn main:app --reload --port 8000"

REM --- Frontend ---
if not exist "%ROOT%frontend\node_modules" (
    echo [frontend] Installing npm packages...
    cd /d "%ROOT%frontend"
    npm install
)

echo [frontend] Starting dev server on http://localhost:5173
start "Agent Runner - Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

REM --- Open browser after a short wait ---
echo Waiting for servers to start...
timeout /t 4 /nobreak >nul
start http://localhost:5173

echo.
echo Both servers are running in separate windows.
echo Close those windows to stop the servers.
