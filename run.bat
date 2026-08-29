@echo off
chcp 65001 >nul
setlocal
set "PROJECT_DIR=%~dp0"

where python >nul 2>&1 || (
  echo [ERROR] Python 3.11+ is required.
  exit /b 1
)
where npm >nul 2>&1 || (
  echo [ERROR] Node.js 20+ is required.
  exit /b 1
)

if not exist "%PROJECT_DIR%frontend\node_modules" (
  call npm --prefix "%PROJECT_DIR%frontend" install || exit /b 1
)

echo Starting backend at http://127.0.0.1:8000
start "MAP-LangGraph-Backend" /D "%PROJECT_DIR%" cmd /k python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
echo Starting frontend at http://127.0.0.1:5173
start "MAP-LangGraph-Frontend" /D "%PROJECT_DIR%frontend" cmd /k npm run dev

echo Open http://127.0.0.1:5173 after both services are ready.
endlocal
