#!/bin/bash
# Agent Status Manager - 追踪多智能体状态
# 用法: ./agent-status.sh [register|update|list|heartbeat] [agent-name] [status]

set -e

STATE_DIR="D:/paper/cc/projects/multi_agent_platform/state"
STATUS_FILE="$STATE_DIR/agent-status.json"
HEARTBEAT_FILE="$STATE_DIR/heartbeat.json"
CONFIG_FILE="$STATE_DIR/agent-config.json"

mkdir -p "$STATE_DIR"

# 状态超时阈值（秒）
TIMEOUT_THRESHOLD=300

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agent-status] $1"
}

# 初始化状态文件
init_state() {
    if [ ! -f "$STATUS_FILE" ]; then
        echo '{"agents":{}}' > "$STATUS_FILE"
    fi
    if [ ! -f "$HEARTBEAT_FILE" ]; then
        echo '{}' > "$HEARTBEAT_FILE"
    fi
    if [ ! -f "$CONFIG_FILE" ]; then
        echo '{"configs":{}}' > "$CONFIG_FILE"
    fi
}

# 注册新 Agent
register_agent() {
    local agent_name="$1"
    local agent_type="${2:-general}"
    local capabilities="${3:-}"

    if [ -z "$agent_name" ]; then
        echo "用法: agent-status.sh register <agent-name> [type] [capabilities]"
        return 1
    fi

    log "注册 Agent: $agent_name (类型: $agent_type)"

    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    if command -v jq &> /dev/null; then
        local temp_file=$(mktemp)
        jq --arg name "$agent_name" \
           --arg type "$agent_type" \
           --arg caps "$capabilities" \
           --arg ts "$timestamp" \
           '.agents[$name] = {"type":$type,"capabilities":$caps,"registered":$ts,"last_seen":$ts,"status":"idle","current_task":null}' \
           "$STATUS_FILE" > "$temp_file" && mv "$temp_file" "$STATUS_FILE"
    fi

    log "Agent 注册成功: $agent_name"
}

# 更新 Agent 状态
update_status() {
    local agent_name="$1"
    local new_status="$2"
    local current_task="${3:-}"

    if [ -z "$agent_name" ] || [ -z "$new_status" ]; then
        echo "用法: agent-status.sh update <agent-name> <status> [current-task]"
        return 1
    fi

    log "更新 Agent 状态: $agent_name → $new_status (任务: $current_task)"

    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    if command -v jq &> /dev/null; then
        local temp_file=$(mktemp)
        jq --arg name "$agent_name" \
           --arg status "$new_status" \
           --arg task "$current_task" \
           --arg ts "$timestamp" \
           '.agents[$name].status = $status | .agents[$name].current_task = $task | .agents[$name].last_seen = $ts' \
           "$STATUS_FILE" > "$temp_file" && mv "$temp_file" "$STATUS_FILE"
    fi
}

# 发送心跳
heartbeat() {
    local agent_name="$1"

    if [ -z "$agent_name" ]; then
        echo "用法: agent-status.sh heartbeat <agent-name>"
        return 1
    fi

    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    if command -v jq &> /dev/null; then
        local temp_file=$(mktemp)
        jq --arg name "$agent_name" \
           --arg ts "$timestamp" \
           '.[$name] = $ts' \
           "$HEARTBEAT_FILE" > "$temp_file" && mv "$temp_file" "$HEARTBEAT_FILE"
    fi
}

# 列出所有 Agent 状态
list_agents() {
    log "列出所有 Agent"

    echo ""
    echo "=== Agent 状态面板 ==="
    echo ""

    if [ -f "$STATUS_FILE" ] && command -v jq &> /dev/null; then
        echo "| Agent | Type | Status | Current Task | Last Seen |"
        echo "|-------|------|--------|--------------|------------|"

        jq -r '.agents | to_entries[] |
            "\(.key) | \(.value.type) | \(.value.status) | \(.value.current_task // "无") | \(.value.last_seen)"' \
            "$STATUS_FILE" 2>/dev/null || echo "无法读取状态"
    else
        echo "状态文件不存在或 jq 不可用"
    fi

    echo ""
}

# 检查超时 Agent
check_timeouts() {
    log "检查超时 Agent"

    local timed_out=0
    local now=$(date +%s)

    if [ -f "$HEARTBEAT_FILE" ] && command -v jq &> /dev/null; then
        local agents=$(jq -r 'to_entries[] | "\(.key)=\(.value)"' "$HEARTBEAT_FILE" 2>/dev/null)

        for entry in $agents; do
            local name="${entry%%=*}"
            local last_beat="${entry#*=}"

            local last_ts=$(date -d "$last_beat" +%s 2>/dev/null || echo 0)
            local diff=$((now - last_ts))

            if [ "$diff" -gt "$TIMEOUT_THRESHOLD" ]; then
                log "Agent 超时: $name (${diff}s 未响应)"

                if command -v jq &> /dev/null; then
                    local temp_file=$(mktemp)
                    jq --arg name "$name" \
                       --arg status "offline" \
                       --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
                       '.agents[$name].status = $status | .agents[$name].last_seen = $ts' \
                       "$STATUS_FILE" > "$temp_file" && mv "$temp_file" "$STATUS_FILE"
                fi

                timed_out=$((timed_out + 1))
            fi
        done
    fi

    log "检查完成，超时 Agent: $timed_out"
}

# 主逻辑
init_state

case "$1" in
    register)
        register_agent "$2" "$3" "$4"
        ;;
    update)
        update_status "$2" "$3" "$4"
        ;;
    heartbeat)
        heartbeat "$2"
        ;;
    list)
        list_agents
        ;;
    check)
        check_timeouts
        ;;
    *)
        echo "Agent Status Manager - 多智能体状态追踪"
        echo ""
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  register <name> [type] [caps]  注册新 Agent"
        echo "  update <name> <status> [task]   更新 Agent 状态"
        echo "  heartbeat <name>                发送心跳"
        echo "  list                           列出所有 Agent"
        echo "  check                           检查超时 Agent"
        echo ""
        echo "状态: idle | busy | processing | completed | offline"
        echo ""
        echo "示例:"
        echo "  $0 register researcher-1 general-purpose 'web-search,code-analysis'"
        echo "  $0 update researcher-1 busy '搜索 AI 最新论文'"
        echo "  $0 heartbeat researcher-1"
        ;;
esac
