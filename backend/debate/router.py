"""
辩论路由 - FastAPI 路由定义
"""
import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from backend import database
from backend.debate import (
    DebateSession,
    SessionStatus,
    DebateAgent,
    DebateMessage,
    DebateReport,
    AgentRole,
    DebateRole,
    KnowledgePoint,
    DebateSessionManager,
    get_debate_manager,
)
from backend.document import DocumentUpload, parse_document, get_document, list_documents

router = APIRouter(prefix="/api", tags=["debate"])


# =============================================================================
# Document APIs
# =============================================================================

@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """
    上传并解析文档

    支持 PDF/DOCX/MD 格式
    """
    # 保存上传的文件
    upload_dir = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".docx", ".md"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 PDF/DOCX/MD")

    # 生成唯一文件名
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, unique_filename)

    # 保存文件
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 解析文档
    upload = parse_document(file_path, file.filename, ext[1:])

    return {
        "document_id": upload.id,
        "file_name": upload.file_name,
        "file_type": upload.file_type,
        "status": upload.status,
        "parse_result": upload.parse_result,
    }


@router.get("/documents")
async def list_docs() -> dict:
    """列出所有上传的文档"""
    docs = list_documents()
    return {
        "documents": [
            {
                "id": d.id,
                "file_name": d.file_name,
                "file_type": d.file_type,
                "status": d.status,
                "created_at": d.created_at.isoformat(),
            }
            for d in docs
        ]
    }


@router.get("/documents/{doc_id}")
async def get_doc(doc_id: str) -> dict:
    """获取文档详情"""
    upload = get_document(doc_id)
    if not upload:
        raise HTTPException(status_code=404, detail="文档不存在")

    return {
        "id": upload.id,
        "file_name": upload.file_name,
        "file_type": upload.file_type,
        "status": upload.status,
        "parse_result": upload.parse_result,
        "created_at": upload.created_at.isoformat(),
    }


# =============================================================================
# Debate Session APIs
# =============================================================================

@router.post("/debate/sessions")
async def create_session(
    title: str = Form(...),
    document_id: Optional[str] = Form(None),
    max_rounds: int = Form(5),
) -> dict:
    """
    创建辩论会话

    Args:
        title: 辩论主题
        document_id: 可选，关联的文档ID
        max_rounds: 最大轮次
    """
    manager = get_debate_manager()

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
        max_rounds=max_rounds,
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


@router.get("/debate/sessions")
async def list_sessions() -> dict:
    """列出所有辩论会话"""
    manager = get_debate_manager()
    sessions = manager.list_sessions()
    return {
        "sessions": [s.to_dict() for s in sessions]
    }


@router.get("/debate/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """获取辩论会话详情"""
    manager = get_debate_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "session": session.to_dict(),
        "agents": [a.to_dict() for a in session.agents],
        "message_count": len(session.messages),
    }


@router.delete("/debate/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """删除辩论会话"""
    manager = get_debate_manager()
    if not manager.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "会话已删除"}


# =============================================================================
# Debate Control APIs
# =============================================================================

@router.post("/debate/sessions/{session_id}/start")
async def start_debate(session_id: str) -> dict:
    """开始辩论"""
    manager = get_debate_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session.status == SessionStatus.ACTIVE:
        return {"success": True, "message": "辩论已在进行中"}

    success = await manager.start_debate(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="无法开始辩论")

    return {"success": True, "message": "辩论已开始"}


@router.post("/debate/sessions/{session_id}/pause")
async def pause_debate(session_id: str) -> dict:
    """暂停辩论"""
    manager = get_debate_manager()
    if not manager.pause_debate(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "辩论已暂停"}


@router.post("/debate/sessions/{session_id}/resume")
async def resume_debate(session_id: str) -> dict:
    """恢复辩论"""
    manager = get_debate_manager()
    if not manager.resume_debate(session_id):
        raise HTTPException(status_code=400, detail="无法恢复辩论")

    return {"success": True, "message": "辩论已恢复"}


@router.post("/debate/sessions/{session_id}/stop")
async def stop_debate(session_id: str) -> dict:
    """停止辩论"""
    manager = get_debate_manager()
    if not manager.stop_debate(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"success": True, "message": "辩论已停止"}


# =============================================================================
# Message APIs
# =============================================================================

@router.get("/debate/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> dict:
    """获取辩论消息"""
    manager = get_debate_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "messages": [m.to_dict() for m in session.messages],
        "message_count": len(session.messages),
    }


@router.get("/debate/sessions/{session_id}/messages/stream")
async def stream_messages(session_id: str):
    """
    SSE 流式获取辩论消息

    前端可以订阅此端点实时接收消息
    """
    manager = get_debate_manager()
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
            if session.status in [SessionStatus.COMPLETED, SessionStatus.FAILED]:
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
# Report APIs
# =============================================================================

@router.get("/debate/sessions/{session_id}/report")
async def get_report(session_id: str) -> dict:
    """获取辩论报告"""
    manager = get_debate_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if not session.report:
        raise HTTPException(status_code=404, detail="报告尚未生成")

    return session.report.to_dict()


# =============================================================================
# WebSocket for Real-time Updates
# =============================================================================

@router.websocket("/ws/debate/{session_id}")
async def debate_websocket(websocket, session_id: str):
    """
    WebSocket 端点用于实时辩论更新

    客户端连接后会自动接收该会话的所有消息
    """
    from fastapi import WebSocket
    from backend.main import manager

    if not hasattr(manager, 'active_connections'):
        manager.active_connections = {}

    ws_key = f"debate_{session_id}"

    if ws_key not in manager.active_connections:
        manager.active_connections[ws_key] = []

    await websocket.accept()
    manager.active_connections[ws_key].append(websocket)

    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            # 这里可以处理客户端发送的消息（如手动发言）
    except Exception:
        pass
    finally:
        if ws_key in manager.active_connections:
            manager.active_connections[ws_key].remove(websocket)
