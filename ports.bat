@echo off
REM ========================================
REM Port Configuration for Multi-Agent Platform
REM ========================================
REM
REM IMPORTANT: Keep BACKEND_PORT and FRONTEND_PORT in sync with:
REM   - backend/app.py (uvicorn port)
REM   - frontend/vite.config.ts (server port)
REM   - frontend/src/types/index.ts (API base URL if configured)
REM
REM Default ports:
SET BACKEND_PORT=8000
SET FRONTEND_PORT=5173
