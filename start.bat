@echo off
setlocal

cd /d "%~dp0"

echo ============================================
echo    OpsWeave Start Script
echo ============================================
echo.

echo [1/2] Starting backend (http://localhost:8001)...
where uv >nul 2>&1
if errorlevel 1 (
    echo uv was not found on PATH. Install uv before starting the backend.
    pause
    exit /b 1
)
if not exist "%~dp0frontend\node_modules\.bin\vite.cmd" (
    echo Frontend dependencies are missing. Run "npm install" in the frontend folder first.
    pause
    exit /b 1
)

start "OpsWeave Backend" /D "%~dp0" cmd /c "uv run python -m uvicorn opsweave.api.main:app --host 127.0.0.1 --port 8001"

echo Waiting for backend health check...
set "BACKEND_READY="
for /l %%i in (1,1,15) do (
    powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/api/health/ping -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "BACKEND_READY=1"
    if defined BACKEND_READY goto backend_ready
    timeout /t 1 >nul
)

if not defined BACKEND_READY (
    echo Backend did not become ready. Check the backend window for errors.
    pause
    exit /b 1
)

:backend_ready
echo [2/2] Starting frontend...
set "FRONTEND_PORT=5173"
set "EXISTING_VITE="
for /f %%p in ('powershell -NoProfile -Command "$listener = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($listener) { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess); if ($p.CommandLine -match 'vite') { 'yes' } else { 'occupied' } }"') do set "EXISTING_VITE=%%p"
if "%EXISTING_VITE%"=="yes" goto frontend_ready
if "%EXISTING_VITE%"=="occupied" (
    set "FRONTEND_PORT=5174"
    echo Port 5173 is occupied by another app; starting Vite at http://localhost:5174...
    start "OpsWeave Frontend" /D "%~dp0frontend" cmd /c "npm run dev -- --host 127.0.0.1 --port 5174 --strictPort"
) else (
    echo Starting Vite at http://localhost:5173...
    start "OpsWeave Frontend" /D "%~dp0frontend" cmd /c "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"
)
:frontend_ready
if "%EXISTING_VITE%"=="yes" echo Reusing existing Vite server at http://localhost:5173

echo.
echo ============================================
echo    Services started
echo    Backend:  http://127.0.0.1:8001
echo    Frontend: http://127.0.0.1:%FRONTEND_PORT%
echo ============================================
echo.

pause
