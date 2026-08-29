#!/bin/bash
# 启动 MCP 监控面板

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DASHBOARD_SCRIPT="$SCRIPT_DIR/dashboard.py"

echo "🔄 生成 MCP 监控面板..."
python "$DASHBOARD_SCRIPT"

echo ""
echo "📊 监控面板已生成"
echo "打开: $PROJECT_ROOT/state/dashboard.html"
echo ""
echo "提示: 定期运行此脚本刷新数据，或使用浏览器自动刷新插件"
