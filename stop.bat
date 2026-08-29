@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Stop Multi-Agent Platform

echo ========================================
echo   Stop Multi-Agent Platform
echo ========================================
echo.

REM Load port config
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
call "%PROJECT_DIR%\ports.bat"

REM Default ports
if not defined BACKEND_PORT set BACKEND_PORT=8000
if not defined FRONTEND_PORT set FRONTEND_PORT=5173

echo Stopping services...
echo.

REM Stop frontend windows
taskkill /F /FI "WINDOWTITLE eq MAP-Frontend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq MAP-Backend*" >nul 2>&1

REM Clean ports
powershell -Command "Get-NetTCPConnection -LocalPort !BACKEND_PORT! -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
powershell -Command "Get-NetTCPConnection -LocalPort !FRONTEND_PORT! -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

REM Clean node and uvicorn
taskkill /F /IM node.exe >nul 2>&1
taskkill /F /FI "COMMANDLINE eq *uvicorn*" >nul 2>&1

echo [OK] Services stopped
echo.
echo ========================================
echo   Stop Complete
echo ========================================
echo.
timeout /t 2 /nobreak >nul
