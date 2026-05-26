@echo off
setlocal EnableDelayedExpansion

REM ══════════════════════════════════════════════════════════════════════════════
REM  Meridian FTTH Data Ingestion Platform — One-Click Launcher
REM
REM  What this script does (fully automatic):
REM    1.  Self-elevates to Administrator (UAC prompt once)
REM    2.  Verifies Python is installed
REM    3.  Creates Python virtual environment (first run only)
REM    4.  Installs ALL Python dependencies from requirements.txt
REM    5.  Downloads and installs nginx to C:\nginx (first run only)
REM    6.  Deploys the nginx reverse-proxy config
REM    7.  Opens Windows Firewall for ports 80 and 8000
REM    8.  Starts the FastAPI backend (port 8000, separate window)
REM    9.  Starts nginx (port 80)
REM    10. Opens the app in your default browser
REM    11. Displays the network URL and login credentials
REM ══════════════════════════════════════════════════════════════════════════════

REM ─── Capture script directory BEFORE elevation (path stays valid after UAC) ──
set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%venv"
set "NGINX_DIR=C:\nginx"
set "NGINX_EXE=%NGINX_DIR%\nginx.exe"
set "NGINX_CONF=%PROJECT_DIR%nginx.conf"
set "PORT=8000"
set "NGINX_VERSION=1.26.2"
set "NGINX_URL=https://nginx.org/download/nginx-%NGINX_VERSION%.zip"
set "NGINX_ZIP=%TEMP%\nginx-%NGINX_VERSION%.zip"

REM ─── Step 0: Self-elevate to Administrator ────────────────────────────────────
net session >nul 2>&1
if errorlevel 1 (
    cls
    echo.
    echo  ╔══════════════════════════════════════════════════════╗
    echo  ║      Meridian FTTH — Requesting Admin Rights         ║
    echo  ╠══════════════════════════════════════════════════════╣
    echo  ║  A Windows UAC prompt will appear.                   ║
    echo  ║  Please click  YES  to continue.                     ║
    echo  ╚══════════════════════════════════════════════════════╝
    echo.
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

REM ─── Running as Administrator ────────────────────────────────────────────────
cd /d "%PROJECT_DIR%"
cls

echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║         Meridian FTTH Data Ingestion Platform                    ║
echo  ║                  One-Click Launcher                              ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.
echo  Project: %PROJECT_DIR%
echo.

REM ══════════════════════════════════════════════════════════════════════════════
REM  STEP 1 — Python
REM ══════════════════════════════════════════════════════════════════════════════
echo  [1/7]  Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo         ERROR: Python not found.
    echo         Install Python 3.11+ from https://python.org/downloads
    echo         IMPORTANT: check "Add Python to PATH" during install.
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo         OK  %%v

REM ══════════════════════════════════════════════════════════════════════════════
REM  STEP 2 — Virtual environment
REM ══════════════════════════════════════════════════════════════════════════════
echo  [2/7]  Setting up Python virtual environment...
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo         Created  %VENV_DIR%
) else (
    echo         OK  venv already exists
)
call "%VENV_DIR%\Scripts\activate.bat"

REM ══════════════════════════════════════════════════════════════════════════════
REM  STEP 3 — Python dependencies
REM ══════════════════════════════════════════════════════════════════════════════
echo  [3/7]  Installing Python dependencies (first run may take ~2-3 min)...
python -m pip install --quiet --upgrade pip
if exist "%PROJECT_DIR%requirements.txt" (
    pip install --quiet -r "%PROJECT_DIR%requirements.txt"
    if errorlevel 1 goto :pip_error
) else (
    REM Fallback: install core packages if requirements.txt is missing
    pip install --quiet fastapi "uvicorn[standard]" python-multipart requests rapidfuzz
    if errorlevel 1 goto :pip_error
)
echo         OK  All packages installed
goto :pip_ok
:pip_error
echo.
echo  ERROR: pip failed to install packages. Check your internet connection.
echo         You can also try: pip install -r requirements.txt manually.
pause
exit /b 1
:pip_ok

REM ══════════════════════════════════════════════════════════════════════════════
REM  STEP 4 — Download and install nginx (first run only)
REM ══════════════════════════════════════════════════════════════════════════════
echo  [4/7]  Setting up nginx...
if not exist "%NGINX_EXE%" (
    echo         nginx not found — downloading version %NGINX_VERSION%...
    echo         URL: %NGINX_URL%
    echo.

    where curl.exe >nul 2>&1
    if not errorlevel 1 (
        curl.exe -L --progress-bar -o "%NGINX_ZIP%" "%NGINX_URL%"
    ) else (
        echo         (Using PowerShell download — this may take a moment)
        powershell -NoProfile -Command "Invoke-WebRequest -Uri '%NGINX_URL%' -OutFile '%NGINX_ZIP%' -UseBasicParsing"
    )

    if not exist "%NGINX_ZIP%" (
        echo.
        echo  ERROR: Download failed. Check your internet connection.
        echo         Manual option: download %NGINX_URL%
        echo                        Extract so that C:\nginx\nginx.exe exists
        pause
        exit /b 1
    )

    echo.
    echo         Extracting to C:\nginx...
    powershell -NoProfile -Command "$z='%NGINX_ZIP%'; Expand-Archive -Path $z -DestinationPath 'C:\' -Force; if (Test-Path 'C:\nginx-%NGINX_VERSION%') { if (Test-Path 'C:\nginx') { Remove-Item 'C:\nginx' -Recurse -Force }; Rename-Item 'C:\nginx-%NGINX_VERSION%' 'nginx' }"
    del "%NGINX_ZIP%" >nul 2>&1

    if not exist "%NGINX_EXE%" (
        echo  ERROR: Extraction failed. nginx.exe not found at %NGINX_EXE%
        pause
        exit /b 1
    )
    echo         OK  nginx installed at %NGINX_DIR%
) else (
    echo         OK  nginx already installed at %NGINX_DIR%
)

REM Deploy project nginx.conf
if exist "%NGINX_CONF%" (
    copy /y "%NGINX_CONF%" "%NGINX_DIR%\conf\nginx.conf" >nul
    echo         OK  nginx.conf deployed
) else (
    echo  WARNING: nginx.conf not found in project — nginx will use its default config
)

REM ══════════════════════════════════════════════════════════════════════════════
REM  STEP 5 — Windows Firewall rules
REM ══════════════════════════════════════════════════════════════════════════════
echo  [5/7]  Configuring Windows Firewall...
netsh advfirewall firewall show rule name="FTTH-HTTP-80" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="FTTH-HTTP-80" dir=in action=allow protocol=TCP localport=80 >nul
    echo         Added  port 80  (nginx / HTTP)
) else (
    echo         OK  port 80 already open
)
netsh advfirewall firewall show rule name="FTTH-API-8000" >nul 2>&1
if errorlevel 1 (
    netsh advfirewall firewall add rule name="FTTH-API-8000" dir=in action=allow protocol=TCP localport=8000 >nul
    echo         Added  port 8000  (FastAPI)
) else (
    echo         OK  port 8000 already open
)

REM ══════════════════════════════════════════════════════════════════════════════
REM  STEP 6 — Start FastAPI backend
REM ══════════════════════════════════════════════════════════════════════════════
echo  [6/7]  Starting FastAPI backend on port %PORT%...

REM Kill any stale process listening on port 8000 (PowerShell is more reliable than netstat/findstr)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 1 /nobreak >nul

REM Write a small launcher so the backend window has its own clean environment
set "LAUNCHER=%TEMP%\ftth_backend_launch.bat"
(
    echo @echo off
    echo title FTTH Backend ^(port %PORT%^)
    echo cd /d "%PROJECT_DIR%"
    echo call "%VENV_DIR%\Scripts\activate.bat"
    echo echo.
    echo echo  =========================================
    echo echo   Meridian FTTH Backend  ^|  port %PORT%
    echo echo  =========================================
    echo echo  API docs:  http://localhost:%PORT%/docs
    echo echo  Close this window to stop the backend.
    echo echo.
    echo python api_server.py
    echo pause
) > "%LAUNCHER%"
start "FTTH-Backend" cmd /k "%LAUNCHER%"
echo         OK  Backend started — waiting 5 s for startup...
timeout /t 5 /nobreak >nul

REM Verify the backend is actually up on port 8000
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue)) { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  WARNING: Backend may not be ready yet — check the "FTTH Backend" window.
    echo           Common causes: database not reachable, missing .env settings.
    echo.
)

REM ══════════════════════════════════════════════════════════════════════════════
REM  STEP 7 — Start nginx
REM ══════════════════════════════════════════════════════════════════════════════
echo  [7/7]  Starting nginx on port 80...
taskkill /f /im nginx.exe >nul 2>&1
timeout /t 1 /nobreak >nul
start "" /D "%NGINX_DIR%" nginx.exe
timeout /t 2 /nobreak >nul

tasklist /fi "IMAGENAME eq nginx.exe" 2>nul | find /i "nginx.exe" >nul
if errorlevel 1 (
    echo.
    echo  ERROR: nginx did not start.
    echo         Check the error log: %NGINX_DIR%\logs\error.log
    pause
    exit /b 1
)
echo         OK  nginx running as reverse proxy on port 80

REM ══════════════════════════════════════════════════════════════════════════════
REM  Get local IP address
REM ══════════════════════════════════════════════════════════════════════════════
set "MY_IP=UNKNOWN"
for /f "tokens=2 delims=:" %%a in ('ipconfig 2^>nul ^| findstr /c:"IPv4 Address"') do (
    set "MY_IP=%%a"
    set "MY_IP=!MY_IP: =!"
    goto :ip_done
)
:ip_done

REM ══════════════════════════════════════════════════════════════════════════════
REM  Open browser automatically
REM ══════════════════════════════════════════════════════════════════════════════
timeout /t 1 /nobreak >nul
start "" http://localhost

REM ══════════════════════════════════════════════════════════════════════════════
REM  Done — display access info and credentials
REM ══════════════════════════════════════════════════════════════════════════════
echo.
echo.
echo  ╔══════════════════════════════════════════════════════════════════════╗
echo  ║                   ALL SERVICES ARE ONLINE                            ║
echo  ╠══════════════════════════════════════════════════════════════════════╣
echo  ║                                                                      ║
echo  ║   Browser opened automatically  ──►  http://localhost               ║
echo  ║                                                                      ║
echo  ║   Network URL (share with team):                                     ║
echo  ║     http://!MY_IP!
echo  ║                                                                      ║
echo  ║   API / Swagger docs:  http://localhost:%PORT%/docs                  ║
echo  ║                                                                      ║
echo  ╠══════════════════════════════════════════════════════════════════════╣
echo  ║                     LOGIN CREDENTIALS                                ║
echo  ╠══════════════════════════════════════════════════════════════════════╣
echo  ║                                                                      ║
echo  ║   Username :  ftth_team                                              ║
echo  ║   Password :  Meridian@2026                                          ║
echo  ║                                                                      ║
echo  ║   (Admin)     admin  /  Meridian@2026                                ║
echo  ║                                                                      ║
echo  ╠══════════════════════════════════════════════════════════════════════╣
echo  ║                      HOW TO STOP                                     ║
echo  ╠══════════════════════════════════════════════════════════════════════╣
echo  ║   1. Close the  "FTTH Backend"  window                               ║
echo  ║   2. Run in CMD:  C:\nginx\nginx.exe -s stop                         ║
echo  ╚══════════════════════════════════════════════════════════════════════╝
echo.
pause
