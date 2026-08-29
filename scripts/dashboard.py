#!/usr/bin/env python3
"""
MCP 监控面板 - 多智能体状态可视化
轻量级版本：读取 JSON 状态文件，生成 HTML 报告
"""

import json
import os
from datetime import datetime
from pathlib import Path

STATE_DIR = Path("D:/paper/cc/projects/multi_agent_platform/state")
OUTPUT_FILE = Path("D:/paper/cc/projects/multi_agent_platform/state/dashboard.html")


def load_json(filepath):
    """加载 JSON 文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def format_timestamp(ts):
    """格式化时间戳"""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime("%H:%M:%S")
    except:
        return ts[11:19] if len(ts) > 11 else ts


def get_status_color(status):
    """根据状态返回颜色"""
    colors = {
        "active": "#22c55e",
        "idle": "#64748b",
        "busy": "#f59e0b",
        "processing": "#3b82f6",
        "completed": "#10b981",
        "offline": "#ef4444",
        "error": "#ef4444"
    }
    return colors.get(status, "#64748b")


def render_dashboard():
    """渲染监控面板"""

    # 加载数据
    agent_status = load_json(STATE_DIR / "agent-status.json")
    task_queue = load_json(STATE_DIR / "task-queue.json")
    worktree_state = load_json(STATE_DIR / "worktree-state.json")
    router_stats = load_json(STATE_DIR / "router-stats.json")
    heartbeat = load_json(STATE_DIR / "heartbeat.json")

    # 计算统计数据
    total_agents = len(agent_status.get('agents', {})) if agent_status else 0
    active_agents = len([a for a in agent_status.get('agents', {}).values()
                         if a.get('status') in ['active', 'busy', 'processing']]) if agent_status else 0
    idle_agents = len([a for a in agent_status.get('agents', {}).values()
                       if a.get('status') == 'idle']) if agent_status else 0

    total_tasks = len(task_queue.get('queue', [])) if task_queue else 0
    queued_tasks = len([t for t in task_queue.get('queue', [])
                        if t.get('status') == 'queued']) if task_queue else 0
    completed_tasks = len([t for t in task_queue.get('queue', [])
                          if t.get('status') == 'completed']) if task_queue else 0

    total_worktrees = len(worktree_state.get('worktrees', {})) if worktree_state else 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 生成 HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP 监控面板 - {now}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            padding: 2rem;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #334155;
        }}
        .header h1 {{
            font-size: 1.5rem;
            color: #f8fafc;
        }}
        .header .time {{
            color: #94a3b8;
            font-size: 0.875rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: #1e293b;
            border-radius: 0.75rem;
            padding: 1.25rem;
            border: 1px solid #334155;
        }}
        .stat-card .label {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}
        .stat-card .value {{
            font-size: 2rem;
            font-weight: 700;
            color: #f8fafc;
        }}
        .stat-card .value.active {{ color: #22c55e; }}
        .stat-card .value.idle {{ color: #64748b; }}
        .stat-card .value.busy {{ color: #f59e0b; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 1.5rem;
        }}
        .panel {{
            background: #1e293b;
            border-radius: 0.75rem;
            border: 1px solid #334155;
            overflow: hidden;
        }}
        .panel-header {{
            padding: 1rem 1.25rem;
            border-bottom: 1px solid #334155;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .panel-header h2 {{
            font-size: 1rem;
            font-weight: 600;
        }}
        .panel-header .count {{
            background: #334155;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
        }}
        .panel-body {{
            padding: 1rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            text-align: left;
            padding: 0.75rem 0.5rem;
            border-bottom: 1px solid #334155;
        }}
        th {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            font-weight: 500;
        }}
        td {{
            font-size: 0.875rem;
        }}
        .status-dot {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 0.5rem;
        }}
        .tag {{
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            background: #334155;
        }}
        .tag.research {{ background: #3b82f6; }}
        .tag.coding {{ background: #8b5cf6; }}
        .tag.writing {{ background: #ec4899; }}
        .tag.review {{ background: #f59e0b; }}
        .tag.browsing {{ background: #22c55e; }}
        .empty {{
            text-align: center;
            color: #64748b;
            padding: 2rem;
        }}
        .refresh {{
            margin-top: 2rem;
            text-align: center;
        }}
        .refresh button {{
            background: #3b82f6;
            color: white;
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 0.5rem;
            cursor: pointer;
            font-size: 0.875rem;
            transition: background 0.2s;
        }}
        .refresh button:hover {{
            background: #2563eb;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 MCP 监控面板</h1>
        <div class="time">最后更新: {now}</div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">总 Agent 数</div>
            <div class="value">{total_agents}</div>
        </div>
        <div class="stat-card">
            <div class="label">活跃 Agent</div>
            <div class="value active">{active_agents}</div>
        </div>
        <div class="stat-card">
            <div class="label">空闲 Agent</div>
            <div class="value idle">{idle_agents}</div>
        </div>
        <div class="stat-card">
            <div class="label">总任务数</div>
            <div class="value">{total_tasks}</div>
        </div>
        <div class="stat-card">
            <div class="label">队列中</div>
            <div class="value busy">{queued_tasks}</div>
        </div>
        <div class="stat-card">
            <div class="label">已完成</div>
            <div class="value active">{completed_tasks}</div>
        </div>
    </div>

    <div class="grid">
        <div class="panel">
            <div class="panel-header">
                <h2>👥 Agent 状态</h2>
                <span class="count">{total_agents}</span>
            </div>
            <div class="panel-body">
                <table>
                    <thead>
                        <tr>
                            <th>Agent</th>
                            <th>状态</th>
                            <th>当前任务</th>
                            <th>最后活跃</th>
                        </tr>
                    </thead>
                    <tbody>
"""

    # Agent 列表
    agents = agent_status.get('agents', {}) if agent_status else {}
    if agents:
        for name, info in agents.items():
            status = info.get('status', 'unknown')
            task = info.get('current_task') or '无'
            last_seen = format_timestamp(info.get('last_seen'))
            color = get_status_color(status)
            html += f"""
                        <tr>
                            <td>{name}</td>
                            <td>
                                <span class="status-dot" style="background:{color}"></span>
                                {status}
                            </td>
                            <td>{task}</td>
                            <td>{last_seen}</td>
                        </tr>"""
    else:
        html += '<tr><td colspan="4" class="empty">暂无 Agent 数据</td></tr>'

    html += """
                    </tbody>
                </table>
            </div>
        </div>

        <div class="panel">
            <div class="panel-header">
                <h2>📋 任务队列</h2>
                <span class="count">"""

    html += f"{total_tasks}</span></div><div class="panel-body><table><thead><tr><th>ID</th><th>类型</th><th>Agent</th><th>状态</th></tr></thead><tbody>"

    # 任务列表
    tasks = task_queue.get('queue', []) if task_queue else []
    if tasks:
        for task in tasks[-10:]:  # 只显示最近10个
            task_id = task.get('id', '')[:20]
            task_type = task.get('type', 'general')
            agent = task.get('agent', 'unassigned')
            status = task.get('status', 'unknown')
            html += f"""<tr>
                            <td>{task_id}...</td>
                            <td><span class="tag {task_type}">{task_type}</span></td>
                            <td>{agent}</td>
                            <td>{status}</td>
                        </tr>"""
    else:
        html += '<tr><td colspan="4" class="empty">暂无任务数据</td></tr>'

    html += """
                    </tbody>
                </table>
            </div>
        </div>

        <div class="panel">
            <div class="panel-header">
                <h2>🌿 Worktree 状态</h2>
                <span class="count">"""

    html += f"{total_worktrees}</span></div><div class="panel-body><table><thead><tr><th>分支</th><th>Agent</th><th>状态</th></tr></thead><tbody>"

    # Worktree 列表
    worktrees = worktree_state.get('worktrees', {}) if worktree_state else {}
    if worktrees:
        for branch, info in worktrees.items():
            agent = info.get('agent', 'unassigned')
            status = info.get('status', 'unknown')
            html += f"""<tr>
                            <td>{branch}</td>
                            <td>{agent}</td>
                            <td>{status}</td>
                        </tr>"""
    else:
        html += '<tr><td colspan="4" class="empty">暂无 Worktree 数据</td></tr>'

    # 路由统计
    total_assigned = router_stats.get('total_assigned', 0) if router_stats else 0
    by_type = router_stats.get('by_type', {}) if router_stats else {}
    by_agent = router_stats.get('by_agent', {}) if router_stats else {}

    html += f"""
                    </tbody>
                </table>
            </div>
        </div>

        <div class="panel">
            <div class="panel-header">
                <h2>📊 路由统计</h2>
            </div>
            <div class="panel-body">
                <table>
                    <tr>
                        <th>指标</th>
                        <th>数值</th>
                    </tr>
                    <tr>
                        <td>总分配任务</td>
                        <td>{total_assigned}</td>
                    </tr>
                </table>
                <h4 style="margin: 1rem 0 0.5rem; font-size: 0.875rem; color: #94a3b8;">按类型</h4>
                <table>
"""

    for t, count in by_type.items():
        html += f'<tr><td>{t}</td><td>{count}</td></tr>'

    html += """
                </table>
                <h4 style="margin: 1rem 0 0.5rem; font-size: 0.875rem; color: #94a3b8;">按 Agent</h4>
                <table>
"""

    for a, count in by_agent.items():
        html += f'<tr><td>{a}</td><td>{count}</td></tr>'

    html += f"""
                </table>
            </div>
        </div>
    </div>

    <div class="refresh">
        <button onclick="location.reload()">🔄 刷新面板</button>
    </div>
</body>
</html>"""

    # 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ 监控面板已更新: {OUTPUT_FILE}")
    return str(OUTPUT_FILE)


if __name__ == "__main__":
    result = render_dashboard()
    print(f"打开 {result} 查看监控面板")
