@echo off
title PRAMAAN - Backend (FastAPI)
cd /d "%~dp0.."

echo ======================================================================
echo                  PRAMAAN Backend (FastAPI :8000)
echo ======================================================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment .venv not found.
    echo Please run python -m venv .venv and install requirements first.
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Starting Uvicorn on http://127.0.0.1:8000...
echo.
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000 --reload

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Backend stopped with an error.
    pause
)
