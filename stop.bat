@echo off
chcp 65001 >nul

echo ============================================
echo    OpsWeave 停止脚本
echo ============================================
echo.

REM 查找并结束占用 8000 端口的进程（后端）
echo 正在停止后端服务...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo 结束进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM 查找并结束占用 5173 或 5174 端口的进程（前端）
echo 正在停止前端服务...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do (
    echo 结束进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5174 ^| findstr LISTENING') do (
    echo 结束进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo ============================================
echo    已停止所有服务
echo ============================================
echo.
pause
