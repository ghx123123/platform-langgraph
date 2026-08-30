# graph_router.py — M7: 教材研读图谱 (文件预览内 选词对话 → 图谱节点)
# 与 material_units/router.py 的其余端点同前缀 /api/material-units
# 数据: unit JSON 内 graph_chats(多轮对话) + graph_nodes(摘要); 图谱节点正文存 graph_notes/*.md
import asyncio
import functools
import re
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from backend.core.config import get_settings
from backend.course_archives.storage import load_archive
from backend.material_units.service import build_graph_chat_context, utc_now
from backend.material_units.storage import (
    delete_graph_note,
    load_graph_note,
    load_material_unit,
    save_graph_note,
    save_material_unit,
)
from backend.workflows.dsh_engine import DshAgentEngine, DshEngineError


router = APIRouter(prefix="/api/material-units", tags=["material-units"])
# 读-改-写整段串行化: "一键导入全部" 会并发调 insert/unlink, 不加锁会
# 出现 lost update (两个请求同时读旧记录, 后写覆盖先写) 或损坏 JSON 500。
_mutation_lock = asyncio.Lock()


def _serialized(fn):
    """把整个 read-modify-write 端点放在进程级 asyncio.Lock 内串行执行."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        async with _mutation_lock:
            return await fn(*args, **kwargs)
    return wrapper


def _engine(request: Request) -> DshAgentEngine:
    """优先用平台当前模型配置的共享引擎(懒创建, 跟随设置面板模型);
    无 workflow_service 时按默认模型各自建一个(不应出现在正常路径)。"""
    workflow_service = getattr(request.app.state, "workflow_service", None)
    if workflow_service is not None:
        model = getattr(workflow_service, "model", None)
        if model is not None and getattr(model, "provider", None) == "dsh":
            return model.ensure_dsh_engine()
    return DshAgentEngine(default_model="deepseek-v4-flash")


async def _load_record(unit_id: str) -> dict:
    try:
        return await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc


async def _save_record(record: dict) -> None:
    await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)


@router.post("/{unit_id}/graph-chat", status_code=200)
@_serialized
async def graph_chat(unit_id: str, payload: dict, request: Request) -> dict:
    """讨论一轮: 选词(quote)+问题(question) → 注入教材上下文 → dsh 回答 → 存回合。
    chat_id 存在则续聊(读历史 rounds); 不存在则新建."""
    material_id = str(payload.get("material_id") or "")
    question = str(payload.get("question") or "").strip()
    quote = str(payload.get("quote") or "").strip()
    chat_id = str(payload.get("chat_id") or "")
    if not material_id or not question:
        raise HTTPException(status_code=422, detail="缺少 material_id 或 question")
    record = await _load_record(unit_id)
    archive = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, record.get("archive_id", ""))
    document = archive.get("_documents", {}).get(material_id, {})
    if not document:
        raise HTTPException(status_code=422, detail="该素材尚无解析正文，请先识别")
    context = build_graph_chat_context(document, quote=quote)
    # 章节归属: 按选词定位; 若是新引用(无 quote) → 空字符串
    from backend.material_units.service import graph_chat_section_title
    section_title = graph_chat_section_title(document, quote=quote)
    # 基于图谱节点的新讨论: context_node_id → 把该节点内容作为附加上下文
    context_node_id = str(payload.get("context_node_id") or "")
    context_node_text = ""
    if context_node_id:
        note = await run_in_threadpool(load_graph_note, get_settings().material_unit_store_path, unit_id, context_node_id)
        if note:
            context_node_text = f"\n\n【已有图谱节点: {note['title']}】\n{note['content'][:1500]}"
    chats = record.setdefault("graph_chats", [])
    chat = next((c for c in chats if c.get("id") == chat_id), None)
    if chat_id and chat is None:
        # 允许新建: chat_id 只是建议, 非必须已存在 — 与前端"继续对话"配合
        chat = None
    if chat is None:
        chat = {
            "id": f"chat-{uuid.uuid4().hex[:10]}",
            "material_id": material_id, "quote": quote, "question": question,
            "section_title": section_title, "context_node_id": context_node_id,
            "rounds": [{"role": "user", "content": question}],
            "created_at": utc_now(), "updated_at": utc_now(),
            "saved_node_id": None,
        }
        chats.append(chat)
        chat_id = chat["id"]
    # 先落库问题(含引用/上下文), 再调用 LLM: 即使调用超时/用户关闭,
    # 问题也不会丢; 前端重进能从 graph-chats 找回该轮。
    rounds = chat.setdefault("rounds", [])
    if not rounds or rounds[-1].get("content") != question:
        rounds.append({"role": "user", "content": question})
    chat["updated_at"] = utc_now()
    record["updated_at"] = utc_now()
    await _save_record(record)
    history = "\n".join(
        f"{'教师' if t.get('role') == 'user' else '助手'}: {(t.get('content') or '')[:600]}"
        for t in chat.get("rounds", [])[-6:]
    )
    system_prompt = (
        "你是教材研读助手，帮助教师深度理解教材内容。"
        "引用教材原文回答时尽量标出**课节归属**；"
        "对教师的教学关注点(易错点/讲法/练习)给出建议；教材未提及的，明确说明后给出通用解释。"
        "回答使用中文，控制在 300 字内。"
    )
    user_prompt = f"{context}{context_node_text}\n\n{('此前对话：\n' + history + '\n') if history else ''}教师问题：{question}"
    try:
        answer = await _engine(request).generate(system_prompt, user_prompt)
    except DshEngineError as exc:
        raise HTTPException(status_code=502, detail=f"AI 讨论失败: {str(exc)[:300]}") from exc
    rounds.append({"role": "assistant", "content": answer})
    chat["updated_at"] = utc_now()
    record["updated_at"] = utc_now()
    await _save_record(record)
    return {"chat_id": chat_id, "answer": answer, "question": question, "quote": quote, "section_title": section_title}


@router.get("/{unit_id}/graph-chats")
async def graph_chats(unit_id: str, material_id: str = "") -> dict:
    record = await _load_record(unit_id)
    chats = record.get("graph_chats") or []
    if material_id:
        chats = [c for c in chats if c.get("material_id") == material_id]
    return {"items": sorted(chats, key=lambda c: c.get("updated_at", ""), reverse=True)}


@router.post("/{unit_id}/graph-chats/{chat_id}/clear")
@_serialized
async def graph_chat_clear(unit_id: str, chat_id: str) -> dict:
    record = await _load_record(unit_id)
    target = next((c for c in record.get("graph_chats") or [] if c.get("id") == chat_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    target["rounds"] = []
    target["updated_at"] = utc_now()
    record["updated_at"] = utc_now()
    await _save_record(record)
    return {"ok": True, "chat_id": chat_id}


@router.post("/{unit_id}/graph-chats/{chat_id}/save")
@_serialized
async def graph_chat_save(unit_id: str, chat_id: str, payload: dict, request: Request) -> dict:
    """把讨论整理为图谱节点: LLM 摘要 → 存单元 graph_notes/*.md + 记入 graph_nodes. 返回 node + md 路径."""
    record = await _load_record(unit_id)
    chat = next((c for c in record.get("graph_chats") or [] if c.get("id") == chat_id), None)
    if chat is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    if not chat.get("rounds"):
        raise HTTPException(status_code=422, detail="对话为空，无法保存")
    system_prompt = (
        "你是教研资料整理器。把教师与助教的教材研读对话整理为**教学补充材料**(markdown)。"
        "结构: ## 主题; ## 要点(<=5条, 每条一句); ## 教学建议(针对易错点/讲授/练习); ## 引用原文.\n"
        "只输出 markdown, 不要解释。"
    )
    conversation = "\n".join(
        f"{'教师' if t.get('role') == 'user' else '助手'}: {(t.get('content') or '')[:500]}"
        for t in chat.get("rounds", [])
    )
    user_prompt = f"教材片段: {chat.get('quote') or ''}\n对话:\n{conversation}"
    try:
        md_content = await _engine(request).generate(system_prompt, user_prompt)
    except DshEngineError as exc:
        raise HTTPException(status_code=502, detail=f"整理失败: {str(exc)[:160]}") from exc
    title = str(payload.get("title") or chat.get("question") or "教材研读补充")[:80]
    node_id = f"graph-{uuid.uuid4().hex[:10]}"
    md_path = await run_in_threadpool(save_graph_note, get_settings().material_unit_store_path, unit_id, node_id, md_content, title)
    parent_id = str(payload.get("parent_id") or "") or None
    record.setdefault("graph_nodes", []).append({
        "id": node_id, "material_id": chat.get("material_id"), "title": title,
        "quote": chat.get("quote") or "", "chat_id": chat_id,
        "section_title": chat.get("section_title") or "",
        "context_node_id": chat.get("context_node_id") or "",
        "parent_id": parent_id,
        "md_file": str(md_path), "created_at": utc_now(), "updated_at": utc_now(),
    })
    chat["saved_node_id"] = node_id
    record["updated_at"] = utc_now()
    await _save_record(record)
    return {"ok": True, "node_id": node_id, "title": title, "md_file": str(md_path), "content": md_content}


@router.get("/{unit_id}/graph-nodes")
async def graph_nodes(unit_id: str, material_id: str = "") -> dict:
    record = await _load_record(unit_id)
    nodes = record.get("graph_nodes") or []
    if material_id:
        nodes = [n for n in nodes if n.get("material_id") == material_id]
    result = []
    for node in nodes:
        content = await run_in_threadpool(load_graph_note, get_settings().material_unit_store_path, unit_id, node.get("id", ""))
        result.append({**node, "content": content.get("content", "") if content else ""})
    return {"items": sorted(result, key=lambda n: n.get("updated_at", ""), reverse=True)}


@router.delete("/{unit_id}/graph-nodes/{node_id}", status_code=200)
@_serialized
async def graph_node_delete(unit_id: str, node_id: str) -> dict:
    """删除图谱节点(含 md 文件与 graph_nodes 记录)."""
    record = await _load_record(unit_id)
    nodes = record.get("graph_nodes") or []
    target = next((n for n in nodes if n.get("id") == node_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="图谱节点不存在")
    await run_in_threadpool(delete_graph_note, get_settings().material_unit_store_path, unit_id, node_id)
    # 级联删除子节点(文献图谱树: 删除父节点时其子树一并删除)
    removed_ids = {node_id}
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if node.get("parent_id") in removed_ids and node.get("id") not in removed_ids:
                removed_ids.add(node.get("id"))
                changed = True
    for rid in removed_ids:
        await run_in_threadpool(delete_graph_note, get_settings().material_unit_store_path, unit_id, rid)
    record["graph_nodes"] = [n for n in nodes if n.get("id") not in removed_ids]
    # 回溯其所在对话, 清除 saved_node_id
    for chat in record.get("graph_chats") or []:
        if chat.get("saved_node_id") in removed_ids:
            chat["saved_node_id"] = None
            chat["updated_at"] = utc_now()
    record["updated_at"] = utc_now()
    await _save_record(record)
    return {"ok": True, "node_id": node_id, "removed": len(removed_ids)}


@router.post("/{unit_id}/graph-nodes/{node_id}/insert-outline")
@_serialized
async def graph_node_insert_outline(unit_id: str, node_id: str, payload: dict, request: Request) -> dict:
    """把图谱节点作为教学补充, 插入知识大纲的指定节点(teacher_note + evidence 标记)."""
    outline_id = str(payload.get("outline_id") or "")
    target_node_id = str(payload.get("node_id") or "")
    if not outline_id or not target_node_id:
        raise HTTPException(status_code=422, detail="缺少 outline_id 或 node_id")
    record = await _load_record(unit_id)
    note = await run_in_threadpool(load_graph_note, get_settings().material_unit_store_path, unit_id, node_id)
    if note is None:
        raise HTTPException(status_code=404, detail="图谱节点不存在")
    latest = None
    for outline in reversed(record.get("knowledge_outlines") or []):
        if outline.get("id") == outline_id:
            latest = outline
            break
    if latest is None:
        raise HTTPException(status_code=404, detail="未找到知识大纲")
    # 目标节点可能在较旧版本(AI优化/重构会重排节点); 若最新版本无该节点, 寻找含该节点的版本
    if not any(str(n.get("id")) == target_node_id for n in (latest.get("nodes") or [])):
        for outline in reversed(record.get("knowledge_outlines") or []):
            if outline.get("id") == outline_id and any(str(n.get("id")) == target_node_id for n in (outline.get("nodes") or [])):
                latest = outline
                break
    node = next((n for n in (latest.get("nodes") or []) if str(n.get("id")) == target_node_id), None)
    if node is None:
        raise HTTPException(status_code=404, detail="大纲内未找到目标节点")
    # C1: 多次导入叠加 —— 已挂载的不覆盖, 只追加新图谱(避免"只有来源"丢失已挂内容)
    existing_marked = [e for e in (node.get("evidence") or []) if str(e.get("locator", "")).startswith("graph:")]
    if any(str(e.get("locator")) == f"graph:{node_id}" for e in existing_marked):
        return {"ok": True, "outline_id": outline_id, "node_id": target_node_id, "title": note["title"], "duplicate": True}
    appended = f"教材研读补充：{note['title']}\n\n{note['content']}"
    # teacher_note 追加(非覆盖)
    node["teacher_note"] = f"{(node.get('teacher_note') or '')}{('' if not node.get('teacher_note') else '\n\n')}{appended}"
    node.setdefault("evidence", []).append({
        "source_type": "teacher", "quote": f"教材研读补充：{note['title']}",
        "label": "教材研读补充", "locator": f"graph:{node_id}",
    })
    latest["updated_at"] = utc_now()
    record["updated_at"] = utc_now()
    await _save_record(record)
    return {"ok": True, "outline_id": outline_id, "node_id": target_node_id, "title": note["title"]}


@router.post("/{unit_id}/graph-nodes/{node_id}/unlink-outline")
@_serialized
async def graph_node_unlink_outline(unit_id: str, node_id: str, payload: dict) -> dict:
    """取消导入: 从大纲节点移除该图谱节点的 evidence(locator=graph:node_id)+同步清理 teacher_note 片段."""
    outline_id = str(payload.get("outline_id") or "")
    target_node_id = str(payload.get("node_id") or "")
    if not outline_id or not target_node_id:
        raise HTTPException(status_code=422, detail="缺少 outline_id 或 node_id")
    record = await _load_record(unit_id)
    # 找到含该 target_node_id 的版本: 用户当前看的是哪个节点, 就取消导入哪个版本。
    # 不能只取"最新版本"——图谱节点可能只存在于较早版本(v4), 最新版(v5)已无该节点。
    latest = None
    found_node = None
    for outline in reversed(record.get("knowledge_outlines") or []):
        if outline.get("id") != outline_id:
            continue
        node = next((n for n in (outline.get("nodes") or []) if str(n.get("id")) == target_node_id), None)
        if node is not None:
            latest = outline
            found_node = node
            break
    if latest is None or found_node is None:
        raise HTTPException(status_code=404, detail="大纲内未找到目标节点（可能该版本已无此节点）")
    node = found_node
    locator = f"graph:{node_id}"
    # 先拿到该图谱节点标题(用于删 teacher_note 对应块), 再删 evidence
    graph_title = ""
    for gnode in record.get("graph_nodes") or []:
        if str(gnode.get("id")) == node_id:
            graph_title = str(gnode.get("title") or "")
            break
    node["evidence"] = [e for e in (node.get("evidence") or []) if str(e.get("locator")) != locator]
    # 清理 teacher_note 对应片段: 删掉以该图谱标题开头的"教材研读补充"块(修复 evidence 先删导致 any() 恒 False 的 bug)
    old_note = node.get("teacher_note") or ""
    target_prefix = f"教材研读补充：{graph_title}"
    blocks = [b for b in re.split(r"\n\n+", old_note) if b.strip()]
    kept = []
    for b in blocks:
        if b.startswith("教材研读补充") and graph_title and b.startswith(target_prefix):
            continue  # 该图谱导入的补充块, 删掉
        kept.append(b)
    node["teacher_note"] = "\n\n".join(kept).strip() if kept else ""
    latest["updated_at"] = utc_now()
    record["updated_at"] = utc_now()
    await _save_record(record)
    return {"ok": True, "outline_id": outline_id, "node_id": target_node_id, "unlinked": True}
