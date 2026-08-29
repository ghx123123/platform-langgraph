"""
Multi-Agent Platform - FastAPI Backend
多智能体协作平台后端
"""
import asyncio
import uuid
import time
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import os
import httpx

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend import database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# MiniMax API Configuration
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = "https://api.minimax.chat/v1"
MINIMAX_MODEL = "MiniMax-M2.7-highspeed"

# Configurable history turns (MiniMax context window ~100K tokens, ~20 turns per 1K tokens)
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))

# ============================================================================
# Enums
# ============================================================================

class AgentStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"

class MessageType(str, Enum):
    CHAT = "chat"
    SUBTASK_REQUEST = "subtask_request"
    REALTIME_REVIEW = "realtime_review"
    CLARIFICATION_REQUEST = "clarification_request"
    RESPONSE = "response"
    ESCALATION = "escalation"
    BROADCAST = "broadcast"

class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"

class MemoryScope(str, Enum):
    PRIVATE = "private"
    TEAM = "team"
    SHARED = "shared"

# ============================================================================
# Data Models
# ============================================================================

class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    role: str  # system prompt
    description: str = ""
    avatar: str = "🤖"
    tools: List[str] = Field(default_factory=list)
    memory_scope: MemoryScope = MemoryScope.PRIVATE
    status: AgentStatus = AgentStatus.OFFLINE
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: MessageType = MessageType.CHAT
    priority: Priority = Priority.P2
    from_agent: str
    to: str  # agent_name, "*", or "topic_name"
    content: Dict[str, Any] = Field(default_factory=dict)
    deadline: str = "immediate"
    callback: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

class Memory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    memory_type: str  # "stm", "ltm", "episodic"
    key: Optional[str] = None
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

# ============================================================================
# Request/Response Models
# ============================================================================

class CreateAgentRequest(BaseModel):
    name: str
    role: str
    description: str = ""
    avatar: str = "🤖"
    tools: List[str] = Field(default_factory=list)
    memory_scope: MemoryScope = MemoryScope.PRIVATE

class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    avatar: Optional[str] = None
    tools: Optional[List[str]] = None
    memory_scope: Optional[MemoryScope] = None

class ThinkRequest(BaseModel):
    prompt: str

class SendMessageRequest(BaseModel):
    msg_type: MessageType = MessageType.CHAT
    priority: Priority = Priority.P2
    to: str
    content: Dict[str, Any] = Field(default_factory=dict)
    deadline: str = "immediate"

class CreateMemoryRequest(BaseModel):
    memory_type: str = "ltm"
    key: Optional[str] = None
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ============================================================================
# App
# ============================================================================

app = FastAPI(
    title="Multi-Agent Platform",
    description="多智能体协作平台后端 API",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# In-Memory Storage (loaded from SQLite on startup)
# ============================================================================

# Initialize database
database.init_db()

# Load agents from database
agents_db = database.load_agents()
agents: Dict[str, Agent] = {
    a["id"]: Agent(**a) for a in agents_db
}
print(f"[DB] Loaded {len(agents)} agents from database")

# Load messages from database
messages_db = database.load_messages()
messages: List[Message] = [
    Message(**m) for m in messages_db
]
print(f"[DB] Loaded {len(messages)} messages from database")

memories: Dict[str, List[Memory]] = {}  # agent_id -> memories

# WebSocket connections
ws_connections: Dict[str, WebSocket] = {}

# ============================================================================
# WebSocket Manager
# ============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, agent_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[agent_id] = websocket

    def disconnect(self, agent_id: str):
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]

    async def send_to_agent(self, agent_id: str, message: dict):
        if agent_id in self.active_connections:
            await self.active_connections[agent_id].send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections.values():
            await connection.send_json(message)

    async def broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast message to all connections in a session"""
        # session_id 作为 agent_id 的前缀
        # 支持 debate_* 和 teaching_* 前缀
        for key, connection in self.active_connections.items():
            if key.startswith(f"debate_{session_id}") or key.startswith(f"teaching_{session_id}"):
                await connection.send_json(message)

manager = ConnectionManager()


# =============================================================================
# Execution Router
# =============================================================================

from backend.execution.router import router as execution_router
app.include_router(execution_router)

# =============================================================================
# Debate Router
# =============================================================================

from backend.debate.router import router as debate_router
app.include_router(debate_router)

# =============================================================================
# Teaching Router
# =============================================================================

from backend.teaching.router import router as teaching_router
app.include_router(teaching_router)

# ============================================================================
# LLM Integration
# ============================================================================

# MiniMax context window is ~100K tokens for Text-01, smaller for M2.7
# We limit history to last 20 turns to stay within limits
MAX_HISTORY_TURNS = 20

async def call_minimax_llm(
    prompt: str,
    system_prompt: str = "",
    conversation_history: List[Dict[str, str]] = None,
    max_tokens: int = 4000,
    timeout_seconds: float = 60.0,
) -> str:
    """Call MiniMax LLM API with conversation history support
    
    Args:
        prompt: 用户提示词
        system_prompt: 系统提示词
        conversation_history: 对话历史
        max_tokens: 最大生成token数（控制响应长度和速度）
        timeout_seconds: 总超时时间
    
    Returns:
        LLM生成的文本内容
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    
    # 日志记录请求信息
    prompt_length = len(prompt)
    logger.info(f"[LLM-{request_id}] 开始调用 | Prompt长度: {prompt_length} | 超时: {timeout_seconds}s")
    
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }

    # 优化：如果 prompt 太长，进行截断
    optimized_prompt = _optimize_prompt_length(prompt, max_length=6000)
    if len(optimized_prompt) < len(prompt):
        logger.warning(f"[LLM-{request_id}] Prompt已优化截断: {len(prompt)} -> {len(optimized_prompt)}")

    messages = []
    if system_prompt:
        # 优化系统提示词长度
        optimized_system = _optimize_prompt_length(system_prompt, max_length=2000)
        messages.append({"role": "system", "content": optimized_system})

    # Add conversation history (last N turns)
    if conversation_history:
        # conversation_history is List of {"role": "user"/"assistant", "content": "..."}
        for hist_msg in conversation_history[-MAX_HISTORY_TURNS:]:
            messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})

    # Add current prompt
    messages.append({"role": "user", "content": optimized_prompt})

    # 精细化的超时配置
    timeout_config = httpx.Timeout(
        connect=10.0,      # 连接超时：10秒
        read=timeout_seconds,  # 读取超时：根据参数动态调整
        write=10.0,        # 写入超时：10秒
        pool=5.0,          # 连接池超时：5秒
    )
    
    # 重试机制
    max_retries = 2
    last_error = None
    
    for attempt in range(max_retries + 1):
        attempt_start = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(
                    f"{MINIMAX_BASE_URL}/chat/completions",
                    headers=headers,
                    json={
                        "model": MINIMAX_MODEL,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": max_tokens,  # 限制生成长度，提高速度
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                elapsed = time.time() - start_time
                content_length = len(content)
                logger.info(f"[LLM-{request_id}] 调用成功 | 耗时: {elapsed:.2f}s | 生成长度: {content_length} | 尝试: {attempt + 1}")
                
                return strip_thinking_tags(content)
                
        except httpx.TimeoutException as e:
            elapsed = time.time() - attempt_start
            last_error = f"Timeout after {elapsed:.2f}s (attempt {attempt + 1})"
            logger.warning(f"[LLM-{request_id}] 超时 | 尝试 {attempt + 1}/{max_retries + 1} | 已耗时: {elapsed:.2f}s")
            
            if attempt < max_retries:
                wait_time = 1.0 * (attempt + 1)  # 递增等待时间
                logger.info(f"[LLM-{request_id}] 等待 {wait_time}s 后重试...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"[LLM-{request_id}] 所有重试均失败")
                
        except httpx.ConnectError as e:
            elapsed = time.time() - attempt_start
            last_error = f"Connection error: {str(e)}"
            logger.error(f"[LLM-{request_id}] 连接错误 | 尝试 {attempt + 1} | 错误: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2.0)
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[LLM-{request_id}] 调用失败 | 耗时: {elapsed:.2f}s | 错误: {type(e).__name__}: {e}")
            return f"Error calling LLM: {str(e)}"
    
    # 所有重试都失败了
    total_elapsed = time.time() - start_time
    logger.error(f"[LLM-{request_id}] 最终失败 | 总耗时: {total_elapsed:.2f}s | 错误: {last_error}")
    return f"Error calling LLM after {max_retries + 1} attempts: {last_error}"


def _optimize_prompt_length(prompt: str, max_length: int = 6000) -> str:
    """优化 prompt 长度，确保不超过限制
    
    策略：
    1. 如果长度在限制内，直接返回
    2. 如果超长，保留开头和结尾，截断中间
    3. 对于代码/JSON内容，优先保留结构
    """
    if len(prompt) <= max_length:
        return prompt
    
    # 保留开头30%和结尾70%（通常结尾更重要）
    head_len = int(max_length * 0.3)
    tail_len = max_length - head_len - 100  # 100字符用于省略标记
    
    head = prompt[:head_len]
    tail = prompt[-tail_len:]
    
    return f"{head}\n\n...[内容已截断，省略 {len(prompt) - head_len - tail_len} 字符]...\n\n{tail}"


def strip_thinking_tags(text: str) -> str:
    """Remove thinking tags from LLM output (e.g., <think>...</think>)"""
    import re
    # Remove <think>...</think> patterns
    text = re.sub(r'<think>[\s\S]*?</think>', '', text)
    # Remove other common thinking markers
    text = re.sub(r'<thinking>[\s\S]*?</thinking>', '', text, flags=re.IGNORECASE)
    return text.strip()


# ============================================================================
# Agent API
# ============================================================================

@app.post("/api/agents", response_model=Agent)
async def create_agent(req: CreateAgentRequest) -> Agent:
    """创建新 Agent"""
    agent = Agent(
        name=req.name,
        role=req.role,
        description=req.description,
        avatar=req.avatar,
        tools=req.tools,
        memory_scope=req.memory_scope,
        status=AgentStatus.ONLINE,
    )
    agents[agent.id] = agent
    memories[agent.id] = []
    # Persist to database
    database.save_agent(agent.model_dump())
    return agent

@app.get("/api/agents", response_model=List[Agent])
async def list_agents() -> List[Agent]:
    """获取 Agent 列表"""
    return list(agents.values())

@app.get("/api/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str) -> Agent:
    """获取 Agent 详情"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents[agent_id]

@app.put("/api/agents/{agent_id}", response_model=Agent)
async def update_agent(agent_id: str, req: UpdateAgentRequest) -> Agent:
    """更新 Agent"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = agents[agent_id]
    update_data = req.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if value is not None:
            setattr(agent, key, value)

    agent.updated_at = datetime.now()
    return agent

@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str) -> dict:
    """删除 Agent"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    del agents[agent_id]
    if agent_id in memories:
        del memories[agent_id]
    # Note: Database records are kept for audit trail

    return {"message": "Agent deleted"}

@app.post("/api/agents/{agent_id}/clone", response_model=Agent)
async def clone_agent(agent_id: str) -> Agent:
    """克隆 Agent"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    original = agents[agent_id]

    # 生成唯一的克隆名称，添加递增编号避免重复
    base_name = f"{original.name} (clone)"
    clone_name = base_name
    counter = 1
    existing_names = {a.name for a in agents.values()}
    while clone_name in existing_names:
        clone_name = f"{base_name} {counter}"
        counter += 1

    clone = Agent(
        name=clone_name,
        role=original.role,
        description=original.description,
        avatar=original.avatar,
        tools=original.tools.copy(),
        memory_scope=original.memory_scope,
        status=AgentStatus.ONLINE,
    )
    agents[clone.id] = clone
    memories[clone.id] = []
    # Persist to database
    database.save_agent(clone.model_dump())
    return clone

@app.post("/api/agents/{agent_id}/think")
async def agent_think(agent_id: str, req: ThinkRequest) -> dict:
    """Agent 对话请求 - 支持多轮对话上下文，持久化存储"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = agents[agent_id]

    # Build system prompt from agent role
    system_prompt = f"You are {agent.name}. {agent.role}"

    # Get conversation history from database (persistent across restarts)
    db_history = database.load_conversation_history(agent_id, limit=MAX_HISTORY_TURNS * 2)

    # Call MiniMax LLM with conversation history
    response = await call_minimax_llm(req.prompt, system_prompt, db_history)

    # Save conversation turns to database for persistence
    database.save_conversation_turn(agent_id, "user", req.prompt)
    database.save_conversation_turn(agent_id, "assistant", response)

    # Store in message history (for in-memory access)
    msg = Message(
        msg_type=MessageType.CHAT,
        from_agent=agent.name,
        to=agent.name,
        content={"prompt": req.prompt, "response": response},
    )
    messages.append(msg)

    # Persist message to database
    database.save_message({
        "id": msg.id,
        "msg_type": msg.msg_type.value,
        "priority": msg.priority.value,
        "from_agent": msg.from_agent,
        "to": msg.to,
        "content": msg.content,
        "deadline": msg.deadline,
        "callback": msg.callback,
        "created_at": msg.created_at.isoformat(),
    })

    return {"response": response, "message_id": msg.id}

@app.get("/api/agents/{agent_id}/status")
async def get_agent_status(agent_id: str) -> dict:
    """获取 Agent 状态"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent_id": agent_id, "status": agents[agent_id].status}

# ============================================================================
# Memory API
# ============================================================================

@app.get("/api/agents/{agent_id}/memories", response_model=List[Memory])
async def list_memories(agent_id: str) -> List[Memory]:
    """获取 Agent 的记忆列表"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return memories.get(agent_id, [])

@app.post("/api/agents/{agent_id}/memories", response_model=Memory)
async def create_memory(agent_id: str, req: CreateMemoryRequest) -> Memory:
    """为 Agent 添加记忆"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    memory = Memory(
        agent_id=agent_id,
        memory_type=req.memory_type,
        key=req.key,
        content=req.content,
        metadata=req.metadata,
    )

    if agent_id not in memories:
        memories[agent_id] = []
    memories[agent_id].append(memory)

    return memory

@app.get("/api/agents/{agent_id}/memories/{memory_id}", response_model=Memory)
async def get_memory(agent_id: str, memory_id: str) -> Memory:
    """获取记忆详情"""
    if agent_id not in memories:
        raise HTTPException(status_code=404, detail="Memory not found")

    for mem in memories[agent_id]:
        if mem.id == memory_id:
            return mem

    raise HTTPException(status_code=404, detail="Memory not found")

@app.delete("/api/agents/{agent_id}/memories/{memory_id}")
async def delete_memory(agent_id: str, memory_id: str) -> dict:
    """删除记忆"""
    if agent_id not in memories:
        raise HTTPException(status_code=404, detail="Agent not found")

    for i, mem in enumerate(memories[agent_id]):
        if mem.id == memory_id:
            memories[agent_id].pop(i)
            return {"message": "Memory deleted"}

    raise HTTPException(status_code=404, detail="Memory not found")

# ============================================================================
# Message API
# ============================================================================

@app.post("/api/messages/send")
async def send_message(req: SendMessageRequest, from_agent: str = "system") -> dict:
    """发送消息"""
    msg = Message(
        msg_type=req.msg_type,
        priority=req.priority,
        from_agent=from_agent,
        to=req.to,
        content=req.content,
        deadline=req.deadline,
    )
    messages.append(msg)

    # If target is online, forward via WebSocket
    for agent in agents.values():
        if agent.name == req.to and agent.id in manager.active_connections:
            await manager.send_to_agent(agent.id, msg.model_dump())

    return {"message_id": msg.id, "status": "sent"}

@app.post("/api/messages/broadcast")
async def broadcast_message(req: SendMessageRequest, from_agent: str = "system") -> dict:
    """广播消息"""
    msg = Message(
        msg_type=MessageType.BROADCAST,
        priority=req.priority,
        from_agent=from_agent,
        to="*",
        content=req.content,
        deadline=req.deadline,
    )
    messages.append(msg)

    await manager.broadcast(msg.model_dump())

    return {"message_id": msg.id, "status": "broadcasted"}

@app.get("/api/messages/history")
async def get_message_history(limit: int = 50) -> List[Message]:
    """获取消息历史"""
    return messages[-limit:]

# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws/{agent_id}")
async def websocket_endpoint(websocket: WebSocket, agent_id: str):
    """WebSocket 连接"""
    if agent_id not in agents:
        await websocket.close(code=4001, reason="Agent not found")
        return

    await manager.connect(agent_id, websocket)
    agents[agent_id].status = AgentStatus.ONLINE

    try:
        while True:
            data = await websocket.receive_json()

            # Handle incoming message
            if data.get("type") == "message":
                msg = Message(
                    msg_type=MessageType(data.get("msg_type", "chat")),
                    from_agent=agents[agent_id].name,
                    to=data.get("to", "*"),
                    content=data.get("content", {}),
                    priority=Priority(data.get("priority", "P2")),
                )
                messages.append(msg)

                # Broadcast to recipient
                if msg.to == "*":
                    await manager.broadcast(msg.model_dump())
                else:
                    for agent in agents.values():
                        if agent.name == msg.to and agent.id in manager.active_connections:
                            await manager.send_to_agent(agent.id, msg.model_dump())

            # Handle ping
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(agent_id)
        agents[agent_id].status = AgentStatus.OFFLINE

# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check() -> dict:
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agents_count": len(agents),
        "messages_count": len(messages),
    }

# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
