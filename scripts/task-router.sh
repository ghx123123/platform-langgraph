#!/bin/bash
# Task Router - 智能任务分配
# 用法: ./task-router.sh [route|queue|stats] [task-description]

set -e

STATE_DIR="D:/paper/cc/projects/multi_agent_platform/state"
TASK_QUEUE_FILE="$STATE_DIR/task-queue.json"
AGENT_CONFIG_FILE="$STATE_DIR/agent-config.json"
ASSIGNMENT_LOG="$STATE_DIR/assignments.log"
STATS_FILE="$STATE_DIR/router-stats.json"

mkdir -p "$STATE_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [task-router] $1" | tee -a "$ASSIGNMENT_LOG"
}

# 初始化状态文件
init_state() {
    if [ ! -f "$TASK_QUEUE_FILE" ]; then
        echo '{"queue":[],"assignments":{}}' > "$TASK_QUEUE_FILE"
    fi
    if [ ! -f "$STATS_FILE" ]; then
        echo '{"total_assigned":0,"by_type":{},"by_agent":{}}' > "$STATS_FILE"
    fi
}

# 分析任务类型
analyze_task() {
    local description="$1"

    # 关键词匹配
    case "$description" in
        *"[research]"*|*"调研"*|*"搜索"*|*"搜索"*)
            echo "research"
            ;;
        *"[code]"*|*"代码"*|*"开发"*|*"实现"*)
            echo "coding"
            ;;
        *"[write]"*|*"写作"*|*"文档"*|*"报告"*)
            echo "writing"
            ;;
        *"[review]"*|*"审查"*|*"检查"*|*"分析"*)
            echo "review"
            ;;
        *"[browser]"*|*"浏览"*|*"网页"*)
            echo "browsing"
            ;;
        *"[agent]"*|*"智能体"*|*"agent"*)
            echo "multi-agent"
            ;;
        *)
            echo "general"
            ;;
    esac
}

# 匹配最佳 Agent
match_agent() {
    local task_type="$1"

    if [ ! -f "$AGENT_CONFIG_FILE" ]; then
        echo "default"
        return
    fi

    # 简单匹配策略
    local best_agent="default"

    if command -v jq &> /dev/null; then
        # 查找支持该类型的 Agent
        local match=$(jq -r --arg type "$task_type" \
            '.configs | to_entries[] |
            select(.value.specialties[] == $type) |
            select(.value.status == "idle") |
            .key' "$AGENT_CONFIG_FILE" 2>/dev/null | head -1)

        if [ -n "$match" ]; then
            best_agent="$match"
        fi
    fi

    echo "$best_agent"
}

# 获取负载最低的 Agent
get_least_loaded() {
    if [ ! -f "$STATS_FILE" ] || ! command -v jq &> /dev/null; then
        echo "default"
        return
    fi

    local least_loaded=$(jq -r '.by_agent | to_entries[] | {agent: .key, count: .value} | sort_by(.count)[0].agent // "default"' "$STATS_FILE" 2>/dev/null)
    echo "$least_loaded"
}

# 路由任务
route_task() {
    local description="$1"
    local priority="${2:-normal}"

    if [ -z "$description" ]; then
        echo "用法: task-router.sh route <task-description> [priority]"
        return 1
    fi

    local task_type=$(analyze_task "$description")
    local target_agent=$(match_agent "$task_type")

    # 如果没有匹配到专用 Agent，选择负载最低的
    if [ "$target_agent" = "default" ]; then
        target_agent=$(get_least_loaded)
    fi

    local task_id="task-$(date +%s)-$RANDOM"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    log "路由任务: [$task_type] → $target_agent"
    log "  描述: $description"

    # 创建任务记录
    local task_record=$(cat <<EOF
{
    "id": "$task_id",
    "description": "$description",
    "type": "$task_type",
    "agent": "$target_agent",
    "priority": "$priority",
    "status": "queued",
    "created": "$timestamp"
}
EOF
)

    # 添加到队列
    if command -v jq &> /dev/null; then
        local temp_file=$(mktemp)
        jq --argjson task "$task_record" \
           '.queue += [$task]' \
           "$TASK_QUEUE_FILE" > "$temp_file" && mv "$temp_file" "$TASK_QUEUE_FILE"

        # 更新统计
        local stats_temp=$(mktemp)
        jq --arg type "$task_type" \
           --arg agent "$target_agent" \
           '.total_assigned += 1 | .by_type[$type] = (.by_type[$type] // 0) + 1 | .by_agent[$agent] = (.by_agent[$agent] // 0) + 1' \
           "$STATS_FILE" > "$stats_temp" && mv "$stats_temp" "$STATS_FILE"
    fi

    echo "$task_id"
    log "  任务ID: $task_id"
}

# 列出队列
list_queue() {
    log "列出任务队列"

    echo ""
    echo "=== 任务队列 ==="
    echo ""

    if [ -f "$TASK_QUEUE_FILE" ] && command -v jq &> /dev/null; then
        echo "| ID | Type | Agent | Priority | Status | Created |"
        echo "|----|------|-------|----------|--------|--------|"

        jq -r '.queue[] |
            "| \(.id) | \(.type) | \(.agent) | \(.priority) | \(.status) | \(.created[11:16]) |"' \
            "$TASK_QUEUE_FILE" 2>/dev/null || echo "无法读取队列"
    else
        echo "队列文件不存在"
    fi

    echo ""
}

# 获取统计
show_stats() {
    log "显示路由统计"

    echo ""
    echo "=== 路由统计 ==="
    echo ""

    if [ -f "$STATS_FILE" ] && command -v jq &> /dev/null; then
        echo "总分配任务: $(jq '.total_assigned' "$STATS_FILE" 2>/dev/null)"
        echo ""
        echo "按类型:"
        jq -r '.by_type | to_entries[] | "  \(.key): \(.value)"' "$STATS_FILE" 2>/dev/null
        echo ""
        echo "按 Agent:"
        jq -r '.by_agent | to_entries[] | "  \(.key): \(.value)"' "$STATS_FILE" 2>/dev/null
    else
        echo "统计文件不存在"
    fi

    echo ""
}

# 完成分配
complete_assignment() {
    local task_id="$1"

    if [ -z "$task_id" ]; then
        echo "用法: task-router.sh complete <task-id>"
        return 1
    fi

    log "完成任务: $task_id"

    if command -v jq &> /dev/null; then
        local temp_file=$(mktemp)
        jq --arg id "$task_id" \
           --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
           '.queue = [.queue[] | if .id == $id then .status = "completed" | .completed = $ts else . end]' \
           "$TASK_QUEUE_FILE" > "$temp_file" && mv "$temp_file" "$TASK_QUEUE_FILE"
    fi
}

# 主逻辑
init_state

case "$1" in
    route)
        route_task "$2" "$3"
        ;;
    queue|list)
        list_queue
        ;;
    stats)
        show_stats
        ;;
    complete)
        complete_assignment "$2"
        ;;
    *)
        echo "Task Router - 智能任务分配"
        echo ""
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  route <description> [priority]  路由任务（自动分析+分配）"
        echo "  queue                             列出任务队列"
        echo "  stats                              显示分配统计"
        echo "  complete <task-id>                标记任务完成"
        echo ""
        echo "任务类型标签:"
        echo "  [research] - 研究调研"
        echo "  [code] - 代码开发"
        echo "  [write] - 写作文档"
        echo "  [review] - 审查分析"
        echo "  [browser] - 网页浏览"
        echo ""
        echo "示例:"
        echo "  $0 route '[research] 调研 AI 最新进展'"
        echo "  $0 route '[code] 开发新功能' high"
        echo "  $0 queue"
        ;;
esac
