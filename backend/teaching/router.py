"""
教学路由 - FastAPI 路由定义
"""
import asyncio
import json
import os
import hashlib
import time
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, Form, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from backend import database
from backend.teaching import (
    TeachingSession,
    TeachingStatus,
    TeachingAgent,
    TeachingMessage,
    TeachingPhase,
    AgentType,
    KnowledgePoint,
    TeachingSessionManager,
    get_teaching_manager,
)
from backend.teaching.evaluation_models import (
    InteractionType,
    LearningObjective,
    ObjectiveAssessment,
    Quiz,
    QuizQuestion,
    QuizAnswer,
    QuizResult,
    QuizType,
)
from backend.document import get_document
from backend.teaching.pdf_report_service import PDFReportService


# =============================================================================
# Request/Response Models
# =============================================================================

class RecordInteractionRequest(BaseModel):
    """记录互动请求模型"""
    agent_id: str
    agent_name: str
    agent_type: str
    content: str
    interaction_type: str
    knowledge_point_id: Optional[str] = None
    parent_id: Optional[str] = None


class CreateLearningObjectiveRequest(BaseModel):
    """创建学习目标请求模型"""
    description: str
    objective_type: str = "knowledge"  # knowledge/skill/attitude
    priority: str = "medium"  # high/medium/low
    related_knowledge_points: Optional[List[str]] = None


class LearningObjectiveResponse(BaseModel):
    """学习目标响应模型"""
    id: str
    session_id: str
    description: str
    objective_type: str
    priority: str
    related_knowledge_points: List[str]
    created_at: str


class ObjectiveAssessmentResponse(BaseModel):
    """目标评估响应模型"""
    id: str
    session_id: str
    objective_id: str
    coverage_score: float
    evidence: str
    gaps: List[str]
    suggestions: List[str]
    created_at: str


class ObjectiveAssessmentSummary(BaseModel):
    """目标评估汇总"""
    avg_score: float
    total_objectives: int
    covered_count: int  # score >= 70
    uncovered_count: int  # score < 70


# =============================================================================
# Quiz Request/Response Models
# =============================================================================

class GenerateQuizRequest(BaseModel):
    """生成测验请求模型"""
    title: Optional[str] = None
    question_count: int = 10
    question_types: List[str] = ["single_choice", "fill_blank"]


class QuizAnswerItem(BaseModel):
    """单个答案项"""
    question_id: str
    answer_text: str


class SubmitQuizRequest(BaseModel):
    """提交测验答案请求模型"""
    answers: List[QuizAnswerItem]


class QuizAnswerResponse(BaseModel):
    """答案响应模型"""
    question_id: str
    is_correct: bool
    score: float
    correct_answer: str
    explanation: str


class QuizResultResponse(BaseModel):
    """测验结果响应模型"""
    total_score: float
    max_score: float
    passed: bool
    answers: List[QuizAnswerResponse]
    weak_knowledge_points: List[str]
    improvement_suggestions: List[str]


class QuizQuestionResponse(BaseModel):
    """测验题目响应模型"""
    id: str
    question_type: str
    question_text: str
    options: List[str]
    explanation: str
    knowledge_point_title: Optional[str]
    difficulty: str
    score: float


class QuizDetailResponse(BaseModel):
    """测验详情响应模型"""
    id: str
    session_id: str
    title: str
    description: str
    time_limit: int
    total_score: float
    passing_score: float
    question_count: int
    questions: List[QuizQuestionResponse]
    created_at: str


router = APIRouter(prefix="/api/teaching", tags=["teaching"])


# =============================================================================
# Teaching Session APIs
# =============================================================================

@router.post("/sessions")
async def create_session(
    title: str = Form(...),
    document_id: Optional[str] = Form(None),
    max_iterations: int = Form(3),
) -> dict:
    """
    创建教学会话

    Args:
        title: 教学主题
        document_id: 可选，关联的文档ID
        max_iterations: 最大迭代次数
    """
    manager = get_teaching_manager()

    # 如果提供了 document_id，获取文档内容
    raw_text = ""
    knowledge_points = []
    if document_id:
        doc = get_document(document_id)
        if doc and doc.parse_result:
            raw_text = doc.parse_result.get("raw_text", "")
            kp_data = doc.parse_result.get("knowledge_points", [])
            knowledge_points = [KnowledgePoint(**kp) for kp in kp_data]

    # 创建会话
    session = manager.create_session(
        title=title,
        document_id=document_id,
        max_iterations=max_iterations,
        knowledge_points=knowledge_points,
        raw_text=raw_text,
    )

    # 自动创建 Agent
    topic = title if not raw_text else raw_text[:500]
    agents = manager.create_agents(session.id, topic=topic)

    return {
        "session": session.to_dict(),
        "agents": [a.to_dict() for a in agents],
    }


@router.get("/sessions")
async def list_sessions() -> dict:
    """列出所有教学会话"""
    manager = get_teaching_manager()
    sessions = manager.list_sessions()
    return {
        "sessions": [s.to_dict() for s in sessions]
    }


def _load_session_from_db(session_id: str) -> Optional[TeachingSession]:
    """从数据库加载会话"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'platform.db')
    if not os.path.exists(db_path):
        return None
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 加载会话
    cursor.execute("SELECT * FROM teaching_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    
    data = dict(row)
    session = TeachingSession.from_dict(data)
    
    # 加载agents
    cursor.execute("SELECT * FROM teaching_agents WHERE session_id = ?", (session_id,))
    agent_rows = cursor.fetchall()
    for agent_data in agent_rows:
        agent = TeachingAgent.from_dict(dict(agent_data))
        session.agents.append(agent)
    
    conn.close()
    return session


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """获取教学会话详情 - 支持从内存或数据库加载"""
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    
    if not session:
        # 从数据库加载
        session = _load_session_from_db(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
    
    # 从数据库加载消息（内存中可能没有）
    messages = _load_messages_from_db(session_id)

    return {
        "session": session.to_dict(),
        "agents": [a.to_dict() for a in session.agents],
        "messages": [m.to_dict() for m in messages],
        "message_count": len(messages),
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """删除教学会话"""
    manager = get_teaching_manager()
    if not manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "会话已删除"}


# =============================================================================
# Teaching Control APIs
# =============================================================================

@router.post("/sessions/{session_id}/start")
async def start_teaching(session_id: str) -> dict:
    """开始教学"""
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session.status == TeachingStatus.TEACHING:
        return {"success": True, "message": "教学已在进行中"}

    success = await manager.start_teaching(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法开始教学")

    return {"success": True, "message": "教学已开始"}


@router.post("/sessions/{session_id}/pause")
async def pause_teaching(session_id: str) -> dict:
    """暂停教学"""
    manager = get_teaching_manager()
    if not manager.pause_teaching(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "教学已暂停"}


@router.post("/sessions/{session_id}/resume")
async def resume_teaching(session_id: str) -> dict:
    """恢复教学"""
    manager = get_teaching_manager()
    if not manager.resume_teaching(session_id):
        raise HTTPException(status_code=400, detail="无法恢复教学")

    return {"success": True, "message": "教学已恢复"}


@router.post("/sessions/{session_id}/stop")
async def stop_teaching(session_id: str) -> dict:
    """停止教学"""
    manager = get_teaching_manager()
    if not manager.stop_teaching(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "教学已停止"}


@router.post("/sessions/{session_id}/next")
async def next_step(session_id: str) -> dict:
    """教学下一步"""
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 如果会话已完成或失败，重置状态
    if session.status in [TeachingStatus.COMPLETED, TeachingStatus.FAILED]:
        session.status = TeachingStatus.TEACHING
        session.updated_at = datetime.now()
        database.update_teaching_session(session_id, {"status": TeachingStatus.TEACHING})

    # 如果会话是暂停状态，先恢复
    if session.status == TeachingStatus.PAUSED:
        session.status = TeachingStatus.TEACHING
        session.updated_at = datetime.now()
        database.update_teaching_session(session_id, {"status": TeachingStatus.TEACHING})

    # 触发下一步教学
    success = await manager.next_teaching_step(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法进行下一步")

    return {"success": True, "message": "已进入下一步"}


@router.post("/sessions/{session_id}/replay")
async def replay_teaching(session_id: str) -> dict:
    """重播教学"""
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 清除消息并重置状态
    session.messages.clear()
    session.current_iteration = 0
    session.current_phase = TeachingPhase.DESIGN
    session.status = TeachingStatus.PENDING

    # 重新开始教学
    success = await manager.start_teaching(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法重播")

    return {"success": True, "message": "开始重播"}


# =============================================================================
# Message APIs
# =============================================================================

def _load_messages_from_db(session_id: str) -> List[TeachingMessage]:
    """从数据库加载教学消息"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'platform.db')
    if not os.path.exists(db_path):
        return []
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM teaching_messages WHERE session_id = ? ORDER BY created_at",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    messages = []
    for row in rows:
        data = dict(row)
        # 解析JSON字段
        if data.get('refs'):
            try:
                data['references'] = json.loads(data['refs'])
            except:
                data['references'] = []
        else:
            data['references'] = []
        
        # 字段映射
        data['agent_type'] = data.get('agent_type', 'teacher')
        data['phase'] = data.get('phase', 'design')
        
        messages.append(TeachingMessage.from_dict(data))
    
    return messages


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> dict:
    """获取教学消息 - 支持从内存或数据库加载"""
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    
    if session and session.messages:
        # 优先从内存获取
        messages = session.messages
    else:
        # 从数据库加载
        messages = _load_messages_from_db(session_id)
    
    return {
        "messages": [m.to_dict() for m in messages],
        "message_count": len(messages),
    }


@router.get("/sessions/{session_id}/messages/stream")
async def stream_messages(session_id: str):
    """
    SSE 流式获取教学消息

    前端可以订阅此端点实时接收消息
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    async def event_generator():
        last_index = 0
        while True:
            # 检查是否有新消息
            if len(session.messages) > last_index:
                new_messages = session.messages[last_index:]
                for msg in new_messages:
                    data = json.dumps({
                        "type": "message",
                        "payload": msg.to_dict(),
                    })
                    yield f"data: {data}\n\n"
                last_index = len(session.messages)

            # 检查状态变化
            if session.status in [TeachingStatus.COMPLETED, TeachingStatus.FAILED]:
                data = json.dumps({
                    "type": "status_change",
                    "payload": {"status": session.status},
                })
                yield f"data: {data}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# =============================================================================
# Teaching Script API
# =============================================================================

@router.get("/sessions/{session_id}/script")
async def get_teaching_script(session_id: str) -> dict:
    """获取讲课稿"""
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "teaching_script": session.teaching_script,
    }


# =============================================================================
# WebSocket for Real-time Updates
# =============================================================================

@router.websocket("/ws/{session_id}")
async def teaching_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket 端点用于实时教学更新

    客户端连接后会自动接收该会话的所有消息
    """
    from backend.main import manager

    if not hasattr(manager, 'active_connections'):
        manager.active_connections = {}

    ws_key = f"teaching_{session_id}"

    if ws_key not in manager.active_connections:
        manager.active_connections[ws_key] = []

    await websocket.accept()
    manager.active_connections[ws_key].append(websocket)

    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            # 这里可以处理客户端发送的消息
    except Exception:
        pass
    finally:
        if ws_key in manager.active_connections:
            manager.active_connections[ws_key].remove(websocket)


# =============================================================================
# Interaction Path APIs
# =============================================================================

@router.post("/sessions/{session_id}/interactions")
async def record_interaction(
    session_id: str,
    request: RecordInteractionRequest,
) -> dict:
    """
    记录互动

    将单次互动记录到会话的 interaction_path 中

    Args:
        session_id: 会话ID
        request: 互动数据，包含：
            - agent_id: Agent ID
            - agent_name: Agent 名称
            - agent_type: Agent 类型 (teacher/student/supervisor)
            - content: 互动内容
            - interaction_type: 互动类型 (question/answer/comment/discussion)
            - knowledge_point_id: 可选，关联的知识点ID
            - parent_id: 可选，父节点ID（用于构建问答链）

    Returns:
        创建的互动节点信息
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 验证 interaction_type
    valid_types = [t.value for t in InteractionType]
    if request.interaction_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 interaction_type: {request.interaction_type}，有效值: {valid_types}"
        )

    # 记录互动
    interaction_data = {
        "agent_id": request.agent_id,
        "agent_name": request.agent_name,
        "agent_type": request.agent_type,
        "content": request.content,
        "interaction_type": request.interaction_type,
        "knowledge_point_id": request.knowledge_point_id,
        "parent_id": request.parent_id,
    }

    node = manager.record_interaction(session_id, interaction_data)
    if not node:
        raise HTTPException(status_code=500, detail="记录互动失败")

    return {
        "success": True,
        "node": node.to_dict(),
    }


@router.get("/sessions/{session_id}/interaction-path")
async def get_interaction_path(session_id: str) -> dict:
    """
    获取完整互动路径

    返回会话的所有互动节点和统计信息

    Args:
        session_id: 会话ID

    Returns:
        包含 session_id、nodes（节点列表）和 statistics（统计数据）的对象
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    path = manager.get_interaction_path(session_id)
    if not path:
        return {
            "session_id": session_id,
            "nodes": [],
            "statistics": {
                "total_interactions": 0,
                "question_count": 0,
                "answer_count": 0,
                "comment_count": 0,
                "qa_coverage": 0,
            },
        }

    return path.to_dict()


# =============================================================================
# Learning Objectives APIs
# =============================================================================

@router.post("/sessions/{session_id}/objectives")
async def create_learning_objective(
    session_id: str,
    request: CreateLearningObjectiveRequest,
) -> dict:
    """
    创建学习目标

    Args:
        session_id: 会话ID
        request: 学习目标数据，包含：
            - description: 目标描述（必填）
            - objective_type: 目标类型，可选 knowledge/skill/attitude（默认: knowledge）
            - priority: 优先级，可选 high/medium/low（默认: medium）
            - related_knowledge_points: 关联的知识点ID列表（可选）

    Returns:
        创建的学习目标对象
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 验证 objective_type
    valid_types = ["knowledge", "skill", "attitude"]
    if request.objective_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 objective_type: {request.objective_type}，有效值: {valid_types}"
        )

    # 验证 priority
    valid_priorities = ["high", "medium", "low"]
    if request.priority not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 priority: {request.priority}，有效值: {valid_priorities}"
        )

    # 创建学习目标
    objective = manager.create_learning_objective(
        session_id=session_id,
        description=request.description,
        objective_type=request.objective_type,
        priority=request.priority,
        related_knowledge_points=request.related_knowledge_points,
    )

    if not objective:
        raise HTTPException(status_code=500, detail="创建学习目标失败")

    return {
        "success": True,
        "objective": objective.to_dict(),
    }


@router.get("/sessions/{session_id}/objectives")
async def get_learning_objectives(session_id: str) -> dict:
    """
    获取学习目标列表

    Args:
        session_id: 会话ID

    Returns:
        学习目标列表
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    objectives = manager.get_learning_objectives(session_id)

    return {
        "objectives": [obj.to_dict() for obj in objectives],
        "total_count": len(objectives),
    }


@router.delete("/sessions/{session_id}/objectives/{objective_id}")
async def delete_learning_objective(session_id: str, objective_id: str) -> dict:
    """
    删除学习目标

    Args:
        session_id: 会话ID
        objective_id: 学习目标ID

    Returns:
        删除结果
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    success = manager.delete_learning_objective(session_id, objective_id)
    if not success:
        raise HTTPException(status_code=404, detail="学习目标不存在")

    return {
        "success": True,
        "message": "学习目标已删除",
    }


# =============================================================================
# Objective Assessment APIs
# =============================================================================

@router.get("/sessions/{session_id}/objective-assessment")
async def get_objective_assessment(session_id: str) -> dict:
    """
    获取学习目标匹配度评估结果

    返回所有学习目标的评估结果和汇总统计

    Args:
        session_id: 会话ID

    Returns:
        包含 objective_assessments（评估列表）和 summary（汇总统计）的对象
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 获取所有评估结果
    assessments = manager.get_objective_assessments(session_id)

    # 计算汇总统计
    total_objectives = len(session.learning_objectives)
    covered_count = sum(1 for a in assessments if a.coverage_score >= 70)
    uncovered_count = len(assessments) - covered_count
    avg_score = sum(a.coverage_score for a in assessments) / len(assessments) if assessments else 0.0

    summary = {
        "avg_score": round(avg_score, 2),
        "total_objectives": total_objectives,
        "assessed_count": len(assessments),
        "covered_count": covered_count,
        "uncovered_count": uncovered_count,
    }

    return {
        "objective_assessments": [ass.to_dict() for ass in assessments],
        "summary": summary,
    }


@router.post("/sessions/{session_id}/objective-assessment")
async def trigger_objective_assessment(
    session_id: str,
    objective_id: Optional[str] = None,
) -> dict:
    """
    触发学习目标匹配度分析

    使用LLM分析教学内容与学习目标的匹配度

    Args:
        session_id: 会话ID
        objective_id: 可选，指定要评估的目标ID。如果不提供，则评估所有目标

    Returns:
        评估结果
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if objective_id:
        # 评估单个目标
        assessment = await manager.assess_objective_coverage(session_id, objective_id)
        if not assessment:
            raise HTTPException(status_code=404, detail="学习目标不存在或评估失败")

        return {
            "success": True,
            "message": "评估完成",
            "assessment": assessment.to_dict(),
        }
    else:
        # 评估所有目标
        assessments = await manager.assess_all_objectives(session_id)

        # 计算汇总统计
        covered_count = sum(1 for a in assessments if a.coverage_score >= 70)
        uncovered_count = len(assessments) - covered_count
        avg_score = sum(a.coverage_score for a in assessments) / len(assessments) if assessments else 0.0

        summary = {
            "avg_score": round(avg_score, 2),
            "total_assessed": len(assessments),
            "covered_count": covered_count,
            "uncovered_count": uncovered_count,
        }

        return {
            "success": True,
            "message": f"已完成 {len(assessments)} 个学习目标的评估",
            "assessments": [ass.to_dict() for ass in assessments],
            "summary": summary,
        }


# =============================================================================
# Quiz APIs
# =============================================================================

@router.post("/sessions/{session_id}/quizzes")
async def generate_quiz(
    session_id: str,
    request: GenerateQuizRequest,
) -> dict:
    """
    自动生成知识点测验

    基于教学内容和知识点自动生成测验题目

    Args:
        session_id: 会话ID
        request: 生成测验请求
            - title: 测验标题（可选）
            - question_count: 题目数量（默认10题）
            - question_types: 题型列表，可选值：single_choice, multi_choice, fill_blank, short_answer

    Returns:
        生成的测验信息（不包含正确答案）
    """
    manager = get_teaching_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 验证题型
    valid_types = ["single_choice", "multi_choice", "fill_blank", "short_answer"]
    for qt in request.question_types:
        if qt not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"无效的题型: {qt}，有效值: {valid_types}"
            )

    # 验证题目数量
    if request.question_count < 1 or request.question_count > 50:
        raise HTTPException(
            status_code=400,
            detail="题目数量必须在1-50之间"
        )

    # 生成测验
    quiz = await manager.generate_quiz(
        session_id=session_id,
        title=request.title,
        question_count=request.question_count,
        question_types=request.question_types,
    )

    if not quiz:
        raise HTTPException(status_code=500, detail="生成测验失败")

    # 返回测验信息（不包含正确答案）
    questions_response = []
    for q in quiz.questions:
        questions_response.append({
            "id": q.id,
            "question_type": q.question_type.value if isinstance(q.question_type, Enum) else q.question_type,
            "question_text": q.question_text,
            "options": q.options,
            "explanation": "",  # 暂不显示解析
            "knowledge_point_title": q.knowledge_point_title,
            "difficulty": q.difficulty,
            "score": q.score,
        })

    return {
        "success": True,
        "quiz": {
            "id": quiz.id,
            "session_id": quiz.session_id,
            "title": quiz.title,
            "description": quiz.description,
            "time_limit": quiz.time_limit,
            "total_score": quiz.total_score,
            "passing_score": quiz.passing_score,
            "question_count": len(quiz.questions),
            "questions": questions_response,
            "created_at": quiz.created_at.isoformat(),
        },
    }


@router.get("/quizzes/{quiz_id}")
async def get_quiz(quiz_id: str) -> dict:
    """
    获取测验详情（包含题目列表）

    Args:
        quiz_id: 测验ID

    Returns:
        测验详情（不包含正确答案）
    """
    manager = get_teaching_manager()
    quiz = manager.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="测验不存在")

    # 返回测验信息（不包含正确答案）
    questions_response = []
    for q in quiz.questions:
        questions_response.append({
            "id": q.id,
            "question_type": q.question_type.value if isinstance(q.question_type, Enum) else q.question_type,
            "question_text": q.question_text,
            "options": q.options,
            "explanation": "",  # 暂不显示解析
            "knowledge_point_title": q.knowledge_point_title,
            "difficulty": q.difficulty,
            "score": q.score,
        })

    return {
        "id": quiz.id,
        "session_id": quiz.session_id,
        "title": quiz.title,
        "description": quiz.description,
        "time_limit": quiz.time_limit,
        "total_score": quiz.total_score,
        "passing_score": quiz.passing_score,
        "question_count": len(quiz.questions),
        "questions": questions_response,
        "created_at": quiz.created_at.isoformat(),
    }


@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz_answers(
    quiz_id: str,
    request: SubmitQuizRequest,
) -> dict:
    """
    提交测验答案并评分

    Args:
        quiz_id: 测验ID
        request: 提交答案请求
            - answers: 答案列表，每项包含 question_id 和 answer_text

    Returns:
        测验结果，包含每题的评分和正确答案
    """
    manager = get_teaching_manager()
    quiz = manager.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="测验不存在")

    if not request.answers:
        raise HTTPException(status_code=400, detail="答案列表不能为空")

    # 提交答案并评分
    answers_data = [{"question_id": a.question_id, "answer_text": a.answer_text} for a in request.answers]
    result = await manager.submit_quiz_answers(quiz_id, answers_data)

    if not result:
        raise HTTPException(status_code=500, detail="评分失败")

    # 构建响应
    answers_response = []
    questions_dict = {q.id: q for q in quiz.questions}

    for answer in result.answers:
        question = questions_dict.get(answer.question_id)
        if question:
            answers_response.append({
                "question_id": answer.question_id,
                "is_correct": answer.is_correct,
                "score": answer.score,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
            })

    return {
        "success": True,
        "result": {
            "total_score": result.total_score,
            "max_score": result.max_score,
            "passed": result.passed,
            "answers": answers_response,
            "weak_knowledge_points": result.weak_knowledge_points,
            "improvement_suggestions": result.improvement_suggestions,
        },
    }


@router.get("/quizzes/{quiz_id}/results")
async def get_quiz_results(quiz_id: str) -> dict:
    """
    获取测验结果

    Args:
        quiz_id: 测验ID

    Returns:
        测验结果，包含总分、通过状态、每题评分和建议
    """
    manager = get_teaching_manager()
    quiz = manager.get_quiz(quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="测验不存在")

    result = manager.get_quiz_results(quiz_id)
    if not result:
        raise HTTPException(status_code=404, detail="测验结果不存在，请先提交答案")

    # 构建响应
    answers_response = []
    questions_dict = {q.id: q for q in quiz.questions}

    for answer in result.answers:
        question = questions_dict.get(answer.question_id)
        if question:
            answers_response.append({
                "question_id": answer.question_id,
                "is_correct": answer.is_correct,
                "score": answer.score,
                "correct_answer": question.correct_answer,
                "explanation": question.explanation,
            })

    return {
        "quiz_id": quiz_id,
        "total_score": result.total_score,
        "max_score": result.max_score,
        "passed": result.passed,
        "answers": answers_response,
        "weak_knowledge_points": result.weak_knowledge_points,
        "improvement_suggestions": result.improvement_suggestions,
        "created_at": result.created_at.isoformat(),
    }


# =============================================================================
# Report Generation APIs
# =============================================================================

# 报告生成任务缓存（内存缓存）
_report_generation_tasks: Dict[str, Dict[str, Any]] = {}

# PDF报告服务实例
_pdf_report_service: Optional[PDFReportService] = None


def get_pdf_report_service() -> PDFReportService:
    """获取PDF报告服务实例（单例模式）"""
    global _pdf_report_service
    if _pdf_report_service is None:
        _pdf_report_service = PDFReportService()
    return _pdf_report_service


def _generate_cache_key(session_id: str, include_quiz: bool, include_interactions: bool) -> str:
    """生成缓存键"""
    key_data = f"{session_id}:{include_quiz}:{include_interactions}"
    return hashlib.md5(key_data.encode()).hexdigest()


def _cleanup_expired_reports():
    """清理过期的报告生成任务记录"""
    current_time = time.time()
    expired_keys = [
        key for key, task in _report_generation_tasks.items()
        if current_time - task.get("timestamp", 0) > 3600  # 1小时后过期
    ]
    for key in expired_keys:
        del _report_generation_tasks[key]


@router.get("/sessions/{session_id}/report/pdf")
async def generate_and_download_report(
    session_id: str,
    include_quiz: bool = Query(True, description="是否包含测验结果"),
    include_interactions: bool = Query(True, description="是否包含互动路径"),
) -> FileResponse:
    """
    生成并下载PDF教学督导报告

    Args:
        session_id: 会话ID
        include_quiz: 是否包含测验结果（默认true）
        include_interactions: 是否包含互动路径（默认true）

    Returns:
        PDF文件下载响应
    """
    manager = get_teaching_manager()

    # 1. 验证会话是否存在
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 2. 验证教学内容是否为空
    if not session.teaching_script and not session.messages:
        raise HTTPException(status_code=400, detail="教学内容为空，无法生成报告")

    # 生成缓存键
    cache_key = _generate_cache_key(session_id, include_quiz, include_interactions)

    try:
        # 3. 准备报告生成所需的数据
        interaction_path = None
        quiz_result = None

        # 获取互动路径数据
        if include_interactions:
            path = manager.get_interaction_path(session_id)
            if path:
                interaction_path = path.to_dict().get("nodes", [])

        # 获取测验结果
        if include_quiz and session.quiz_id:
            quiz_result = manager.get_quiz_results(session.quiz_id)

        # 4. 生成PDF报告
        service = get_pdf_report_service()

        # 记录生成任务状态
        _report_generation_tasks[cache_key] = {
            "session_id": session_id,
            "status": "generating",
            "timestamp": time.time(),
            "progress": 0,
        }

        # 生成报告
        pdf_path = service.generate_pdf_report(
            session=session,
            interaction_path=interaction_path,
            quiz_result=quiz_result,
        )

        # 5. 检查文件是否成功生成
        if not os.path.exists(pdf_path):
            _report_generation_tasks[cache_key]["status"] = "failed"
            raise HTTPException(status_code=500, detail="报告生成失败：文件未创建")

        # 更新任务状态为完成
        _report_generation_tasks[cache_key]["status"] = "completed"
        _report_generation_tasks[cache_key]["file_path"] = pdf_path
        _report_generation_tasks[cache_key]["progress"] = 100

        # 6. 构建文件名：教学分析报告-{课程名称}-{YYYYMMDD}.pdf
        date_str = datetime.now().strftime("%Y%m%d")
        # 清理课程名称中的非法字符，使用ASCII字符
        safe_title = "".join(c for c in session.title if c.isalnum() or c in "_- ").strip()
        if not safe_title:
            safe_title = "unnamed"
        # 使用ASCII文件名避免HTTP头编码问题
        ascii_filename = f"teaching_report_{safe_title}_{date_str}.pdf"
        # 中文文件名用于FileResponse的filename参数（浏览器会处理）
        display_filename = f"教学分析报告-{safe_title}-{date_str}.pdf"

        # 7. 返回文件下载响应
        return FileResponse(
            path=pdf_path,
            filename=ascii_filename,
            media_type="application/pdf",
            headers={
                "X-Report-Generated": "true",
                "X-Session-ID": session_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        # 记录失败状态
        _report_generation_tasks[cache_key] = {
            "session_id": session_id,
            "status": "failed",
            "timestamp": time.time(),
            "error": str(e),
        }
        raise HTTPException(
            status_code=500,
            detail=f"报告生成失败: {str(e)}"
        )


@router.get("/sessions/{session_id}/report/status")
async def get_report_generation_status(session_id: str) -> dict:
    """
    获取报告生成状态（用于大报告异步生成）

    Args:
        session_id: 会话ID

    Returns:
        报告生成状态信息
    """
    manager = get_teaching_manager()

    # 验证会话是否存在
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 清理过期任务
    _cleanup_expired_reports()

    # 查找该会话的报告生成任务
    session_tasks = [
        task for task in _report_generation_tasks.values()
        if task.get("session_id") == session_id
    ]

    if not session_tasks:
        return {
            "session_id": session_id,
            "status": "not_started",
            "message": "暂无报告生成任务",
            "progress": 0,
        }

    # 获取最新的任务
    latest_task = max(session_tasks, key=lambda x: x.get("timestamp", 0))

    response = {
        "session_id": session_id,
        "status": latest_task.get("status", "unknown"),
        "progress": latest_task.get("progress", 0),
        "timestamp": latest_task.get("timestamp"),
    }

    if latest_task.get("status") == "failed":
        response["error"] = latest_task.get("error", "未知错误")
    elif latest_task.get("status") == "completed":
        response["message"] = "报告生成完成"
        response["file_path"] = latest_task.get("file_path")
    elif latest_task.get("status") == "generating":
        response["message"] = "报告生成中，请稍候"

    return response
