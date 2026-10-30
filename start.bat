@echo off
setlocal

cd /d "%~dp0"

echo ============================================
echo    OpsWeave Start Script
echo ============================================
echo.

echo [1/2] Starting backend (http://localhost:8000)...
start "OpsWeave Backend" /D "%~dp0" cmd /k "uv run python -m uvicorn opsweave.api.main:app --host 0.0.0.0 --port 8000"

timeout /t 3 >nul

echo [2/2] Starting frontend (http://localhost:5173)...
start "OpsWeave Frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo.
echo ============================================
echo    Done!
echo    Backend:  http://localhost:8000
echo    Frontend: http://localhost:5173
echo ============================================
echo.

pause
