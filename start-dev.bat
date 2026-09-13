@echo off
setlocal enabledelayedexpansion

title PRAMAAN Workstation Launcher

echo ======================================================================
echo    PRAMAAN v1 — EVIDENCE BEFORE TRUST
echo    Offline Integrity Assurance Workstation for Computer Vision
echo ======================================================================
echo.
echo Initializing Desktop Workstation Shell...
echo Root Directory: %~dp0
cd /d "%~dp0"

:: Ensure local environment
set PRAMAAN_AI_ENABLED=false
set NODE_ENV=development

:: Check if npx/electron is available
where npx >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js / npx is not found in PATH. Please install Node.js.
    pause
    exit /b 1
)

echo Starting Electron Desktop Shell...
call npx electron electron/main.cjs

echo.
echo [PRAMAAN] Workstation session finished cleanly.
endlocal
