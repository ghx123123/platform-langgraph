#!/usr/bin/env python3
"""
Smart Task Router - 智能任务分配引擎
根据任务类型、Agent 专长和当前负载自动分配任务
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

STATE_DIR = Path("D:/paper/cc/projects/multi_agent_platform/state")
CONFIG_FILE = STATE_DIR / "agent-config.json"
STATUS_FILE = STATE_DIR / "agent-status.json"
STATS_FILE = STATE_DIR / "router-stats.json"
QUEUE_FILE = STATE_DIR / "task-queue.json"
LOG_FILE = STATE_DIR / "smart-router.log"


def log(msg: str):
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    print(entry)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(entry + "\n")
    except:
        pass


def load_json(filepath) -> Optional[dict]:
    """加载 JSON 文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def save_json(filepath, data):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 任务类型关键词映射
TASK_KEYWORDS = {
    "research": [
        "调研", "搜索", "研究", "调查", "分析趋势",
        "research", "search", "investigate", "survey"
    ],
    "coding": [
        "代码", "开发", "实现", "编程", "修复",
        "code", "develop", "implement", "program", "fix", "build"
    ],
    "writing": [
        "写作", "写文档", "写报告", "写文章", "撰写",
        "write", "document", "report", "article"
    ],
    "review": [
        "审查", "检查", "审核", "review", "audit", "check"
    ],
    "browsing": [
        "浏览", "网页", "抓取", "爬取",
        "browse", "web", "scrape", "crawl"
    ],
    "multi-agent": [
        "智能体", "多智能体", "agent", "multi-agent", "协作"
    ]
}


def analyze_task_type(description: str) -> str:
    """分析任务类型"""
    description_lower = description.lower()

    scores = {}
    for task_type, keywords in TASK_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword.lower() in description_lower:
                score += 1
        if score > 0:
            scores[task_type] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


def get_agent_load(agent_name: str) -> int:
    """获取 Agent 当前负载（正在处理的任务数）"""
    status = load_json(STATUS_FILE)
    if not status:
        return 0

    agents = status.get('agents', {})
    agent_info = agents.get(agent_name, {})
    current_task = agent_info.get('current_task')
    return 1 if current_task else 0


def get_agent_specialties(agent_name: str) -> List[str]:
    """获取 Agent 专长列表"""
    config = load_json(CONFIG_FILE)
    if not config:
        return []

    configs = config.get('configs', {})
    agent_config = configs.get(agent_name, {})
    return agent_config.get('specialties', [])


def match_best_agent(task_type: str, preferred_agent: Optional[str] = None) -> str:
    """匹配最佳 Agent"""

    # 1. 如果指定了首选 Agent 且可用
    if preferred_agent:
        agent_status = load_json(STATUS_FILE)
        if agent_status:
            agents = agent_status.get('agents', {})
            agent_info = agents.get(preferred_agent, {})
            if agent_info.get('status') in ['idle', 'busy']:
                load = get_agent_load(preferred_agent)
                max_load = 2  # 默认最大负载
                if load < max_load:
                    log(f"  → 使用首选 Agent: {preferred_agent}")
                    return preferred_agent

    # 2. 根据专长匹配
    config = load_json(CONFIG_FILE)
    if config:
        configs = config.get('configs', {})
        candidates = []

        for agent_name, agent_config in configs.items():
            specialties = agent_config.get('specialties', [])
            status_info = load_json(STATUS_FILE)
            if status_info:
                agent_status = status_info.get('agents', {}).get(agent_name, {})
                status = agent_status.get('status', 'offline')
                if status in ['idle', 'busy']:
                    load = get_agent_load(agent_name)
                    max_load = agent_config.get('max_concurrent_tasks', 2)

                    if load < max_load and task_type in specialties:
                        score = len(specialties) - specialties.index(task_type)
                        candidates.append((agent_name, score, load))

        if candidates:
            # 按分数排序，分数相同时按负载排序
            candidates.sort(key=lambda x: (-x[1], x[2]))
            best_agent = candidates[0][0]
            log(f"  → 专长匹配: {best_agent} (类型: {task_type})")
            return best_agent

    # 3. 负载均衡模式：选择最空闲的 Agent
    status = load_json(STATUS_FILE)
    if status:
        agents = status.get('agents', {})
        idle_agents = [
            (name, get_agent_load(name))
            for name, info in agents.items()
            if info.get('status') == 'idle'
        ]
        if idle_agents:
            idle_agents.sort(key=lambda x: x[1])
            best_agent = idle_agents[0][0]
            log(f"  → 负载均衡: {best_agent}")
            return best_agent

    # 4. 默认回退
    log("  → 默认回退: default")
    return "default"


def route_task(description: str, priority: str = "normal",
               preferred_agent: Optional[str] = None) -> Dict:
    """路由任务"""

    # 1. 分析任务类型
    task_type = analyze_task_type(description)
    log(f"路由任务: [{task_type}] {description[:50]}...")

    # 2. 匹配最佳 Agent
    target_agent = match_best_agent(task_type, preferred_agent)

    # 3. 创建任务记录
    task_id = f"task-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hash(description) % 10000:04d}"
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    task_record = {
        "id": task_id,
        "description": description,
        "type": task_type,
        "agent": target_agent,
        "priority": priority,
        "status": "queued",
        "created": timestamp,
        "auto_routed": True
    }

    # 4. 更新队列
    queue = load_json(QUEUE_FILE) or {"queue": [], "assignments": {}}
    queue["queue"].append(task_record)

    # 5. 更新统计
    stats = load_json(STATS_FILE) or {"total_assigned": 0, "by_type": {}, "by_agent": {}}
    stats["total_assigned"] += 1
    stats["by_type"][task_type] = stats["by_type"].get(task_type, 0) + 1
    stats["by_agent"][target_agent] = stats["by_agent"].get(target_agent, 0) + 1

    # 6. 保存
    save_json(QUEUE_FILE, queue)
    save_json(STATS_FILE, stats)

    log(f"  → 任务ID: {task_id}")
    log(f"  → 分配给: {target_agent}")

    return task_record


def get_recommendations(task_description: str) -> List[Dict]:
    """获取任务分配建议"""
    task_type = analyze_task_type(task_description)

    config = load_json(CONFIG_FILE)
    status = load_json(STATUS_FILE)

    recommendations = []

    if config:
        configs = config.get('configs', {})

        for agent_name, agent_config in configs.items():
            specialties = agent_config.get('specialties', [])
            is_match = task_type in specialties

            current_status = "offline"
            current_load = 0
            if status:
                agent_info = status.get('agents', {}).get(agent_name, {})
                current_status = agent_info.get('status', 'offline')
                current_load = get_agent_load(agent_name)

            recommendations.append({
                "agent": agent_name,
                "match": is_match,
                "specialties": specialties,
                "status": current_status,
                "load": current_load,
                "max_load": agent_config.get('max_concurrent_tasks', 2)
            })

    # 按匹配度和负载排序
    recommendations.sort(key=lambda x: (-x["match"], x["load"]))

    return recommendations


def print_usage():
    """打印用法"""
    print("""
Smart Task Router - 智能任务分配

用法:
    python smart_router.py route <description> [options]
    python smart_router.py recommend <description>
    python smart_router.py stats

选项:
    route <description>     路由任务（自动分析+分配）
      --agent <name>       指定首选 Agent
      --priority <level>   设置优先级 (low/normal/high)

    recommend <description> 获取分配建议

    stats                  显示路由统计

示例:
    python smart_router.py route "[research] 调研 AI 最新进展"
    python smart_router.py route "[code] 开发新功能" --agent coder-1 --priority high
    python smart_router.py recommend "搜索最新论文"
    python smart_router.py stats
""")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1]

    if command == "route":
        description = sys.argv[2] if len(sys.argv) > 2 else ""
        if not description:
            print("错误: 需要提供任务描述")
            print_usage()
            sys.exit(1)

        priority = "normal"
        preferred_agent = None

        # 解析选项
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--priority" and i + 1 < len(args):
                priority = args[i + 1]
                i += 2
            elif args[i] == "--agent" and i + 1 < len(args):
                preferred_agent = args[i + 1]
                i += 2
            else:
                i += 1

        result = route_task(description, priority, preferred_agent)
        print(f"\n[Task routed]")
        print(f"   ID: {result['id']}")
        print(f"   Type: {result['type']}")
        print(f"   Agent: {result['agent']}")
        print(f"   Priority: {result['priority']}")

    elif command == "recommend":
        description = sys.argv[2] if len(sys.argv) > 2 else ""
        if not description:
            print("错误: 需要提供任务描述")
            print_usage()
            sys.exit(1)

        task_type = analyze_task_type(description)
        print(f"\n[Task analysis]: {description[:50]}...")
        print(f"   Detected type: {task_type}")
        print(f"\n[Agent recommendations]")
        print("-" * 60)

        recommendations = get_recommendations(description)
        for i, rec in enumerate(recommendations, 1):
            match_icon = "[Y]" if rec["match"] else "[N]"
            print(f"   {match_icon} {rec['agent']}")
            print(f"      Specialties: {', '.join(rec['specialties'])}")
            print(f"      Status: {rec['status']} | Load: {rec['load']}/{rec['max_load']}")
            print()

    elif command == "stats":
        stats = load_json(STATS_FILE) or {}

        print("\n[Router Stats]")
        print("-" * 40)
        print(f"Total assigned: {stats.get('total_assigned', 0)}")

        print("\nBy type:")
        for t, count in stats.get('by_type', {}).items():
            print(f"  {t}: {count}")

        print("\nBy agent:")
        for a, count in stats.get('by_agent', {}).items():
            print(f"  {a}: {count}")

    else:
        print_usage()
