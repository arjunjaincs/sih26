@echo off
setlocal enabledelayedexpansion

title PRAMAAN - Project Launcher

:: Resolve root directory without trailing backslash
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

cd /d "%ROOT_DIR%"

echo ======================================================================
echo                   PRAMAAN - Evidence Before Trust
echo                Offline CV Integrity Assurance System
echo ======================================================================
echo.

:: 1. Check Python Virtual Environment
set "VENV_ACTIVATE=%ROOT_DIR%\.venv\Scripts\activate.bat"
if exist "%VENV_ACTIVATE%" (
    echo [OK] Python virtual environment found: .venv
) else (
    echo [ERROR] Virtual environment not found at:
    echo         %ROOT_DIR%\.venv
    echo.
    echo Please create the virtual environment first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -e .
    echo.
    pause
    exit /b 1
)

:: 2. Check Node.js
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Node.js is not installed or not found in system PATH.
    echo Please install Node.js [v18 or higher] from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

:: 3. Check Frontend Dependencies
if not exist "%ROOT_DIR%\frontend\node_modules" (
    echo [!] Frontend dependencies not found. Installing now...
    cd /d "%ROOT_DIR%\frontend"
    call npm.cmd install
    if !errorlevel! neq 0 (
        echo [ERROR] npm install failed! Please check your network or Node setup.
        pause
        exit /b 1
    )
    cd /d "%ROOT_DIR%"
) else (
    echo [OK] Frontend dependencies verified.
)

:: 4. Check for port conflicts
netstat -aon | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [!] Warning: Port 8000 is already in use.
    echo     If an older PRAMAAN backend is running, run stop.bat first.
)

netstat -aon | findstr ":5173" | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo [!] Warning: Port 5173 is already in use.
    echo     If an older Vite server is running, run stop.bat first.
)

echo.
echo [*] Starting Backend [FastAPI on http://127.0.0.1:8000]...
start "PRAMAAN - Backend (FastAPI :8000)" cmd /k ""%ROOT_DIR%\scripts\start-backend.bat""

echo [*] Starting Frontend [Vite on http://localhost:5173]...
start "PRAMAAN - Frontend (Vite :5173)" cmd /k ""%ROOT_DIR%\scripts\start-frontend.bat""

echo.
echo ======================================================================
echo  PRAMAAN services are launching in separate terminal windows!
echo.
echo  - Frontend Web UI:  http://localhost:5173
echo  - Backend API:      http://127.0.0.1:8000
echo  - API Swagger Docs: http://127.0.0.1:8000/docs
echo.
echo  Keep the terminal windows open while using PRAMAAN.
echo  To shut down both services at any time, run stop.bat.
echo ======================================================================
echo.

if "%~1"=="--no-browser" (
    echo Browser auto-open skipped [--no-browser flag passed].
) else (
    echo Opening http://localhost:5173 in default browser...
    ping -n 4 127.0.0.1 >nul
    start http://localhost:5173
)
