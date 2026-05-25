@echo off
setlocal

REM ─── Configuration ────────────────────────────────────────────────────────────
set BACKEND_DIR=%~dp0
set FRONTEND_DIR=%USERPROFILE%\OneDrive - Cyient Ltd\Documents\FTTH_PROD_frontend\react-app
set VENV_DIR=%BACKEND_DIR%venv

REM ─── Python Virtual Environment ──────────────────────────────────────────────
echo [1/5] Setting up Python virtual environment...
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment. Ensure Python 3.11+ is installed.
        pause
        exit /b 1
    )
    echo       Created venv at %VENV_DIR%
) else (
    echo       venv already exists.
)

call "%VENV_DIR%\Scripts\activate.bat"

REM ─── Install Backend Dependencies ────────────────────────────────────────────
echo [2/5] Installing Python dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r "%BACKEND_DIR%requirements.txt"
pip install --quiet fastapi uvicorn python-multipart
if errorlevel 1 (
    echo ERROR: Failed to install Python dependencies.
    pause
    exit /b 1
)
echo       Backend dependencies installed.

REM ─── Install Frontend Dependencies ───────────────────────────────────────────
echo [3/5] Installing frontend dependencies...
pushd "%FRONTEND_DIR%"
if not exist "node_modules\vite" (
    call npm install --silent
    if errorlevel 1 (
        echo ERROR: Failed to install frontend dependencies. Ensure Node.js is installed.
        popd
        pause
        exit /b 1
    )
    echo       Frontend dependencies installed.
) else (
    echo       Frontend node_modules already present.
)
popd

REM ─── Start Backend ───────────────────────────────────────────────────────────
echo [4/5] Starting FastAPI backend on port 8000...
pushd "%BACKEND_DIR%"
start "FTTH-Backend" cmd /k ""%VENV_DIR%\Scripts\activate.bat" && python api_server.py"
popd

REM Give backend a moment to start
timeout /t 3 /nobreak >nul

REM ─── Start Frontend ──────────────────────────────────────────────────────────
echo [5/5] Starting React frontend (Vite dev server)...
pushd "%FRONTEND_DIR%"
start "FTTH-Frontend" cmd /k "npm run dev"
popd

REM ─── Done ────────────────────────────────────────────────────────────────────
echo.
echo ══════════════════════════════════════════════════════════════
echo   FTTH Data Ingestion Platform is running!
echo.
echo   Backend API:  http://localhost:8000
echo   Frontend UI:  http://localhost:5173  (or :5174 if 5173 is busy)
echo   Database:     PostgreSQL on localhost:5432
echo.
echo   Close the "FTTH-Backend" and "FTTH-Frontend" windows to stop.
echo ══════════════════════════════════════════════════════════════
echo.
pause
