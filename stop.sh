#!/bin/bash
# ============================================================================
# Multi-Agent Platform 停止脚本
# ============================================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-3000}

echo "========================================"
echo "  停止 Multi-Agent Platform"
echo "========================================"
echo ""

# 从文件读取 PIDs
if [ -f "$PROJECT_DIR/.pids" ]; then
    read -r BACKEND_PID FRONTEND_PID < "$PROJECT_DIR/.pids"
    echo "从 .pids 读取到 PID: $BACKEND_PID, $FRONTEND_PID"
fi

# 清理端口进程 (使用 netstat 替代 lsof)
cleanup_port() {
    local port=$1
    # 使用 netstat 获取占用端口的 PID
    local pid=$(netstat -ano | grep ":$port.*LISTENING" | awk '{print $5}' | head -1)
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
        echo "终止占用端口 $port 的进程 (PID: $pid)"
        taskkill //F //PID "$pid" 2>/dev/null || true
    else
        echo "端口 $port 无进程占用"
    fi
}

echo "清理后端端口 $BACKEND_PORT..."
cleanup_port $BACKEND_PORT

echo "清理前端端口 $FRONTEND_PORT..."
cleanup_port $FRONTEND_PORT

# 清理 PID 文件
if [ -f "$PROJECT_DIR/.pids" ]; then
    rm "$PROJECT_DIR/.pids"
fi

echo ""
echo "停止完成"
