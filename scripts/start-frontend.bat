@echo off
title PRAMAAN - Frontend (Vite)
cd /d "%~dp0..\frontend"

echo ======================================================================
echo                  PRAMAAN Frontend (Vite :5173)
echo ======================================================================
echo.

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found in PATH.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo [*] Installing dependencies...
    call npm.cmd install
)

echo [*] Starting Vite development server on http://localhost:5173...
echo.
call npm.cmd run dev

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Frontend server stopped with an error.
    pause
)
