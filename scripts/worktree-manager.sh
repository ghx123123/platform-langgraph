#!/bin/bash
# Worktree Manager - 多智能体工作区管理
# 用法: ./worktree-manager.sh [create|list|cleanup|remove] [branch-name]

set -e

PROJECT_ROOT="D:/paper/cc"
WORKTREE_BASE="$PROJECT_ROOT/.claude/worktrees"
STATE_FILE="$PROJECT_ROOT/projects/multi_agent_platform/state/worktree-state.json"
LOG_FILE="$PROJECT_ROOT/projects/multi_agent_platform/state/worktree.log"

# 确保目录存在
mkdir -p "$WORKTREE_BASE" "$PROJECT_ROOT/projects/multi_agent_platform/state"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 初始化状态文件
init_state() {
    if [ ! -f "$STATE_FILE" ]; then
        echo '{"worktrees":{},"agents":{}}' > "$STATE_FILE"
    fi
}

# 创建 worktree
create_worktree() {
    local branch_name="$1"
    local agent_name="${2:-default}"

    if [ -z "$branch_name" ]; then
        echo "用法: worktree-manager.sh create <branch-name> [agent-name]"
        return 1
    fi

    local worktree_path="$WORKTREE_BASE/$branch_name"

    if [ -d "$worktree_path" ]; then
        log "Worktree 已存在: $branch_name"
        return 1
    fi

    log "创建 worktree: $branch_name (Agent: $agent_name)"

    # 创建 worktree
    git worktree add "$worktree_path" -b "$branch_name"

    # 更新状态
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local new_entry=$(cat <<EOF
"$branch_name": {
    "path": "$worktree_path",
    "agent": "$agent_name",
    "created": "$timestamp",
    "status": "active"
}
EOF
)

    # 使用 jq 更新 JSON（如果可用）
    if command -v jq &> /dev/null; then
        local temp_file=$(mktemp)
        jq --arg branch "$branch_name" \
           --arg path "$worktree_path" \
           --arg agent "$agent_name" \
           --arg timestamp "$timestamp" \
           '.worktrees[$branch] = {"path":$path,"agent":$agent,"created":$timestamp,"status":"active"}' \
           "$STATE_FILE" > "$temp_file" && mv "$temp_file" "$STATE_FILE"
    fi

    log "Worktree 创建成功: $branch_name → $worktree_path"
    echo "$worktree_path"
}

# 列出所有 worktree
list_worktrees() {
    log "列出所有 worktree"

    echo ""
    echo "=== Worktree 列表 ==="
    echo ""

    if [ -f "$STATE_FILE" ] && command -v jq &> /dev/null; then
        jq -r '.worktrees | to_entries[] | "\(.key) | Agent: \(.value.agent) | Path: \(.value.path) | Status: \(.value.status)"' "$STATE_FILE" 2>/dev/null || echo "无法读取状态"
    else
        git worktree list
    fi

    echo ""
}

# 清理孤立 worktree
cleanup_worktrees() {
    log "清理孤立 worktree"

    local removed=0

    if [ -f "$STATE_FILE" ] && command -v jq &> /dev/null; then
        # 获取所有 worktree 路径
        local paths=$(jq -r '.worktrees[].path' "$STATE_FILE" 2>/dev/null)

        for path in $paths; do
            if [ ! -d "$path" ]; then
                local branch=$(basename "$path")
                log "移除孤立 worktree 记录: $branch"

                local temp_file=$(mktemp)
                jq --arg branch "$branch" 'del(.worktrees[$branch])' "$STATE_FILE" > "$temp_file" && mv "$temp_file" "$STATE_FILE"
                removed=$((removed + 1))
            fi
        done
    fi

    log "清理完成，移除 $removed 条记录"
}

# 移除 worktree
remove_worktree() {
    local branch_name="$1"
    local force="${2:-false}"

    if [ -z "$branch_name" ]; then
        echo "用法: worktree-manager.sh remove <branch-name> [--force]"
        return 1
    fi

    local worktree_path="$WORKTREE_BASE/$branch_name"

    if [ ! -d "$worktree_path" ]; then
        log "Worktree 不存在: $branch_name"
        return 1
    fi

    log "移除 worktree: $branch_name"

    # 移除 worktree
    git worktree remove "$worktree_path" $force

    # 更新状态
    if [ -f "$STATE_FILE" ] && command -v jq &> /dev/null; then
        local temp_file=$(mktemp)
        jq --arg branch "$branch_name" 'del(.worktrees[$branch])' "$STATE_FILE" > "$temp_file" && mv "$temp_file" "$STATE_FILE"
    fi

    log "Worktree 移除成功: $branch_name"
}

# 主逻辑
init_state

case "$1" in
    create)
        create_worktree "$2" "$3"
        ;;
    list)
        list_worktrees
        ;;
    cleanup)
        cleanup_worktrees
        ;;
    remove|rm)
        remove_worktree "$2" "$3"
        ;;
    *)
        echo "Worktree Manager - 多智能体工作区管理"
        echo ""
        echo "用法: $0 <command> [args]"
        echo ""
        echo "命令:"
        echo "  create <branch> [agent]  创建 worktree"
        echo "  list                        列出所有 worktree"
        echo "  cleanup                     清理孤立记录"
        echo "  remove <branch> [--force]   移除 worktree"
        echo ""
        echo "示例:"
        echo "  $0 create feature-ai-agent researcher-1"
        echo "  $0 list"
        echo "  $0 remove feature-ai-agent"
        ;;
esac
