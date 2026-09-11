@echo off
setlocal enabledelayedexpansion

title PRAMAAN - Stop Services

echo ======================================================================
echo                   PRAMAAN - Stopping Services
echo ======================================================================
echo.

set "STOPPED=0"

:: Check & terminate backend on port 8000
echo [*] Checking for backend processes on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [+] Stopping backend process [PID: %%a]...
    taskkill /F /PID %%a >nul 2>&1
    set "STOPPED=1"
)

:: Check & terminate frontend on port 5173 / 5174
echo [*] Checking for frontend processes on port 5173/5174...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 :5174" ^| findstr "LISTENING"') do (
    echo [+] Stopping frontend process [PID: %%a]...
    taskkill /F /PID %%a >nul 2>&1
    set "STOPPED=1"
)

echo.
if "!STOPPED!"=="1" (
    echo [OK] All PRAMAAN services stopped successfully.
) else (
    echo [i] No running PRAMAAN processes detected on ports 8000 or 5173.
)
echo ======================================================================
echo.
ping -n 3 127.0.0.1 >nul
