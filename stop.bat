@echo off
chcp 65001 >nul

echo ============================================
echo    OpsWeave 停止脚本
echo ============================================
echo.

REM 精确匹配本地监听端口，避免误匹配 18000 等端口
echo 正在停止后端服务...
call :stop_port 8001

echo 正在停止前端服务...
call :stop_port 5173
call :stop_port 5174

echo.
echo ============================================
echo    已停止所有服务
echo ============================================
echo.
pause
exit /b

:stop_port
set "PORT=%~1"
for /f "tokens=1,2,3,4,5" %%a in ('netstat -ano -p tcp ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    if "%%b"=="LISTENING" if "%%c"=="%PORT%" (
        echo 结束本地端口 %PORT% 对应进程 PID: %%e
        taskkill /PID %%e >nul 2>&1
    )
)
exit /b
