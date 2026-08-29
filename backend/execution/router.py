"""
Execution Router - 多智能体执行状态可视化 API
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/execution", tags=["execution"])

# ============================================================================
# In-Memory Execution State (shared with main app via module-level state)
# ============================================================================

# Active sessions and their state
_execution_state: Dict[str, Any] = {
    "sessions": {},  # session_id -> session data
    "agent_nodes": {},  # session_id -> list of agent nodes
    "agent_edges": {},  # session_id -> list of agent edges
    "tasks": {},  # task_id -> task data
    "timeline_events": [],  # list of all events
}


# ============================================================================
# Request/Response Models
# ============================================================================

class AgentNodeModel(BaseModel):
    id: str
    label: str
    type: str  # proponent, opponent, teacher, student, etc.
    status: str = "idle"  # idle, thinking, speaking, waiting, completed, error
    avatar: str = "🤖"
    current_task: Optional[str] = None
    message_count: int = 0


class AgentEdgeModel(BaseModel):
    id: str
    source: str
    target: str
    type: str = "message"  # message, subtask, broadcast
    count: int = 0
    last_message: Optional[str] = None
    animated: bool = False


class TaskExecutionModel(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str = "queued"  # queued, running, completed, failed
    priority: str = "medium"  # low, medium, high, critical
    assigned_agent: Optional[str] = None
    progress: int = 0  # 0-100
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


class TimelineEventModel(BaseModel):
    id: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    type: str  # task_start, task_complete, task_fail, agent_join, etc.
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ExecutionStatisticsModel(BaseModel):
    total_duration: int = 0  # seconds
    total_tokens: int = 0
    total_messages: int = 0
    average_response_time: float = 0  # ms
    task_completion_rate: float = 0  # 0-1
    agent_activity: Dict[str, int] = Field(default_factory=dict)  # agentId -> message count


class SessionGraphModel(BaseModel):
    nodes: List[AgentNodeModel] = []
    edges: List[AgentEdgeModel] = []


# ============================================================================
# State Management Endpoints
# ============================================================================

@router.get("/status")
async def get_execution_status():
    """获取当前执行状态概览"""
    sessions = _execution_state.get("sessions", {})
    tasks = _execution_state.get("tasks", {})

    running_tasks = [t for t in tasks.values() if t.get("status") == "running"]
    completed_tasks = [t for t in tasks.values() if t.get("status") == "completed"]

    return {
        "active_sessions": [
            {
                "id": sid,
                "type": sess.get("type"),
                "status": sess.get("status"),
                "title": sess.get("title"),
                "start_time": sess.get("start_time"),
                "agent_count": len(_execution_state.get("agent_nodes", {}).get(sid, [])),
            }
            for sid, sess in sessions.items()
            if sess.get("status") in ("active", "pending")
        ],
        "task_summary": {
            "total": len(tasks),
            "queued": len([t for t in tasks.values() if t.get("status") == "queued"]),
            "running": len(running_tasks),
            "completed": len(completed_tasks),
            "failed": len([t for t in tasks.values() if t.get("status") == "failed"]),
        },
        "message_flow_stats": {
            "total_events": len(_execution_state.get("timeline_events", [])),
            "total_edges": sum(
                len(edges) for edges in _execution_state.get("agent_edges", {}).values()
            ),
        },
    }


@router.get("/sessions/{session_id}/graph")
async def get_session_graph(session_id: str) -> SessionGraphModel:
    """获取 Agent 协作图谱数据"""
    nodes = _execution_state.get("agent_nodes", {}).get(session_id, [])
    edges = _execution_state.get("agent_edges", {}).get(session_id, [])

    return SessionGraphModel(
        nodes=[AgentNodeModel(**n) for n in nodes],
        edges=[AgentEdgeModel(**e) for e in edges],
    )


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(session_id: str) -> Dict[str, Any]:
    """获取执行时间线事件"""
    events = _execution_state.get("timeline_events", [])

    # Filter events for this session
    session_events = [
        e for e in events
        if e.get("session_id") == session_id or not e.get("session_id")
    ]

    return {
        "events": events,
        "total": len(events),
    }


@router.get("/sessions/{session_id}/statistics")
async def get_session_statistics(session_id: str) -> ExecutionStatisticsModel:
    """获取会话执行统计"""
    nodes = _execution_state.get("agent_nodes", {}).get(session_id, [])
    tasks = _execution_state.get("tasks", {})

    # Calculate statistics
    total_tasks = len(tasks)
    completed_tasks = len([t for t in tasks.values() if t.get("status") == "completed"])

    # Calculate agent activity
    agent_activity = {}
    for node in nodes:
        agent_activity[node.get("id", node.get("label", "unknown"))] = node.get(
            "message_count", 0
        )

    return ExecutionStatisticsModel(
        total_duration=0,  # Would need to track start/end times
        total_tokens=0,  # Would need to track from LLM calls
        total_messages=sum(n.get("message_count", 0) for n in nodes),
        average_response_time=0,  # Would need to track per-message
        task_completion_rate=completed_tasks / total_tasks if total_tasks > 0 else 0,
        agent_activity=agent_activity,
    )


# ============================================================================
# State Update Endpoints (called by debate/teaching routers)
# ============================================================================

@router.post("/sessions")
async def create_session(session_id: str, session_type: str, title: str):
    """创建执行会话"""
    if "sessions" not in _execution_state:
        _execution_state["sessions"] = {}
    if "agent_nodes" not in _execution_state:
        _execution_state["agent_nodes"] = {}
    if "agent_edges" not in _execution_state:
        _execution_state["agent_edges"] = {}

    _execution_state["sessions"][session_id] = {
        "id": session_id,
        "type": session_type,
        "title": title,
        "status": "active",
        "start_time": datetime.now().isoformat(),
    }
    _execution_state["agent_nodes"][session_id] = []
    _execution_state["agent_edges"][session_id] = []

    return {"session_id": session_id, "status": "created"}


@router.post("/sessions/{session_id}/agents")
async def add_agent_to_session(session_id: str, agent: AgentNodeModel):
    """添加 Agent 到会话"""
    if session_id not in _execution_state.get("agent_nodes", {}):
        _execution_state.setdefault("agent_nodes", {})[session_id] = []

    _execution_state["agent_nodes"][session_id].append(agent.model_dump())

    # Add timeline event
    _add_timeline_event(
        session_id=session_id,
        event_type="agent_join",
        agent_id=agent.id,
        details={"agent_label": agent.label, "agent_type": agent.type},
    )

    return {"status": "added", "agent_id": agent.id}


@router.post("/sessions/{session_id}/edges")
async def add_edge_to_session(session_id: str, edge: AgentEdgeModel):
    """添加边到会话（Agent 之间的通信）"""
    if session_id not in _execution_state.get("agent_edges", {}):
        _execution_state.setdefault("agent_edges", {})[session_id] = []

    # Check if edge already exists
    existing = _execution_state["agent_edges"][session_id]
    for i, e in enumerate(existing):
        if e.get("source") == edge.source and e.get("target") == edge.target:
            # Update existing edge
            existing[i]["count"] = edge.count
            existing[i]["last_message"] = edge.last_message
            existing[i]["animated"] = True
            return {"status": "updated", "edge_id": e.get("id")}

    # Add new edge
    _execution_state["agent_edges"][session_id].append(edge.model_dump())

    # Add timeline event
    _add_timeline_event(
        session_id=session_id,
        event_type="message_sent",
        agent_id=edge.source,
        details={
            "source": edge.source,
            "target": edge.target,
            "message_preview": edge.last_message[:50] if edge.last_message else None,
        },
    )

    return {"status": "added", "edge_id": edge.id}


@router.put("/sessions/{session_id}/agents/{agent_id}/status")
async def update_agent_status(
    session_id: str, agent_id: str, status: str, current_task: Optional[str] = None
):
    """更新 Agent 状态"""
    nodes = _execution_state.get("agent_nodes", {}).get(session_id, [])

    for node in nodes:
        if node.get("id") == agent_id:
            node["status"] = status
            if current_task:
                node["current_task"] = current_task
            return {"status": "updated", "agent_id": agent_id}

    raise HTTPException(status_code=404, detail="Agent not found in session")


@router.post("/tasks")
async def create_task(task: TaskExecutionModel):
    """创建任务"""
    if "tasks" not in _execution_state:
        _execution_state["tasks"] = {}

    _execution_state["tasks"][task.id] = task.model_dump()

    # Add timeline event
    _add_timeline_event(
        session_id=task.assigned_agent,  # Using agent as session proxy
        event_type="task_start",
        task_id=task.id,
        details={"task_title": task.title},
    )

    return {"status": "created", "task_id": task.id}


@router.put("/tasks/{task_id}/status")
async def update_task_status(
    task_id: str, status: str, result: Optional[str] = None
):
    """更新任务状态"""
    tasks = _execution_state.get("tasks", {})

    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    tasks[task_id]["status"] = status
    if result:
        tasks[task_id]["result"] = result
    if status in ("completed", "failed"):
        tasks[task_id]["completed_at"] = datetime.now().isoformat()

    # Add timeline event
    _add_timeline_event(
        session_id=tasks[task_id].get("assigned_agent"),
        event_type="task_complete" if status == "completed" else "task_fail",
        task_id=task_id,
        details={"task_title": tasks[task_id].get("title"), "result": result},
    )

    return {"status": "updated", "task_id": task_id}


# ============================================================================
# Helper Functions
# ============================================================================

def _add_timeline_event(
    session_id: Optional[str],
    event_type: str,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
):
    """添加时间线事件"""
    if "timeline_events" not in _execution_state:
        _execution_state["timeline_events"] = []

    event = TimelineEventModel(
        id=f"evt_{len(_execution_state['timeline_events']) + 1}",
        type=event_type,
        agent_id=agent_id,
        task_id=task_id,
        details=details or {},
    )

    _execution_state["timeline_events"].append(event.model_dump())

    # Keep only last 1000 events
    if len(_execution_state["timeline_events"]) > 1000:
        _execution_state["timeline_events"] = _execution_state["timeline_events"][-1000:]


# ============================================================================
# WebSocket Integration for Real-time Updates
# ============================================================================

def get_execution_state():
    """获取执行状态（供其他模块使用）"""
    return _execution_state


def update_agent_message_count(session_id: str, agent_id: str, increment: int = 1):
    """更新 Agent 消息计数"""
    nodes = _execution_state.get("agent_nodes", {}).get(session_id, [])

    for node in nodes:
        if node.get("id") == agent_id:
            node["message_count"] = node.get("message_count", 0) + increment
            return

    # Agent not found, create if session exists
    if session_id in _execution_state.get("agent_nodes", {}):
        _execution_state["agent_nodes"][session_id].append({
            "id": agent_id,
            "label": agent_id,
            "type": "unknown",
            "status": "idle",
            "message_count": increment,
        })