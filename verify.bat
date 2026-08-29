@echo off
chcp 65001 >nul
title Multi-Agent Platform Verification

echo ========================================
echo   Multi-Agent Platform 验证脚本
echo ========================================
echo.

set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

REM Kill any existing processes
echo [清理] 停止已有服务...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
timeout /t 2 /nobreak >nul

REM ============================================================================
REM Start Backend
REM ============================================================================
echo [启动] 后端服务 (http://localhost:8000)...
start "MAP-Backend" cmd /k "cd /d %PROJECT_DIR% && python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000"

REM Wait for backend to be ready
echo [等待] 后端启动...
timeout /t 3 /nobreak >nul

REM Test backend health
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [错误] 后端启动失败！
    pause
    exit /b 1
)
echo [OK] 后端运行正常

REM ============================================================================
REM Start Frontend
REM ============================================================================
echo [启动] 前端服务 (http://localhost:5173)...
start "MAP-Frontend" cmd /k "cd /d %PROJECT_DIR%\frontend && npm run dev"

echo [等待] 前端启动...
timeout /t 5 /nobreak >nul

REM ============================================================================
REM Open Browser
REM ============================================================================
echo [打开] 浏览器...
start http://localhost:5173

REM ============================================================================
REM Run API Tests
REM ============================================================================
echo.
echo ========================================
echo   API 功能测试
echo ========================================
echo.

REM Test 1: Health Check
echo [Test 1] Health Check...
curl -s http://localhost:8000/health
echo.

REM Test 2: Create Agent
echo [Test 2] 创建测试Agent...
curl -s -X POST "http://localhost:8000/api/agents" -H "Content-Type: application/json" -d "{\"name\": \"验证助手\", \"role\": \"你是一个测试助手\", \"description\": \"验证脚本创建的测试Agent\"}"
echo.

REM Test 3: List Agents
echo [Test 3] 获取Agent列表...
curl -s http://localhost:8000/api/agents
echo.

REM Test 4: Get Messages History
echo [Test 4] 获取消息历史...
curl -s "http://localhost:8000/api/messages/history"
echo.

echo ========================================
echo   验证完成！
echo ========================================
echo.
echo   前端: http://localhost:5173
echo   后端: http://localhost:8000
echo   API文档: http://localhost:8000/docs
echo.
echo   请在浏览器中进行以下测试:
echo   1. 创建 Agent
echo   2. 与 Agent 对话
echo   3. 查看/添加记忆
echo   4. 测试工具面板
echo.
echo ========================================
echo.
pause
