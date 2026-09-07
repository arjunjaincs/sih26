@echo off
setlocal

title PRAMAAN - Server Launcher
echo =======================================================
echo          PRAMAAN AI ASSURANCE PLATFORM
echo               Starting Local Servers
echo =======================================================
echo.

set "PROJECT_ROOT=%~dp0"

echo [1/2] Launching Backend Server (FastAPI on http://localhost:8000)...
start "PRAMAAN Backend (FastAPI)" cmd /k "cd /d "%PROJECT_ROOT%backend" && if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) && python -m uvicorn app.main:app --reload --port 8000"

echo [2/2] Launching Frontend Server (Vite on http://localhost:5173)...
start "PRAMAAN Frontend (Vite)" cmd /k "cd /d "%PROJECT_ROOT%frontend" && npm run dev"

echo.
echo =======================================================
echo  Servers launched in separate terminal windows!
echo.
echo  - Frontend Web UI:  http://localhost:5173
echo  - Backend API:      http://localhost:8000
echo  - Interactive Docs: http://localhost:8000/docs
echo.
echo  Keep those two terminal windows open while running.
echo  To stop a server, close its window or press Ctrl+C.
echo =======================================================
echo.
pause
