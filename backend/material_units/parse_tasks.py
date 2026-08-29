# parse_tasks.py — 资料单元 后台异步解析 (并发2, 进度持久化)
# 仅服务于 material_units 路径 (导入资料单元后后台解析), 不影响 course_archives 主流程。
# 模式复用: 参照 material_units/router.py 的 refine-task (后台任务 + 任务ID + 轮询)。
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.course_archives.service import extract_course_archive_materials
from backend.course_archives.storage import save_archive, load_archive
from backend.documents.service import parse_document

# 并发2: 内存安全
_MAX_WORKERS = 2

_pool = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="tc-parse")
_lock = threading.RLock()
# task_id -> {unit_id, status, progress, materials: [{id, name, status, progress, message}], errors}
_tasks: dict[str, dict[str, Any]] = {}


def has_running_task(unit_id: str, material_id: str) -> bool:
    """同文件（unit+material）是否有未完成(排队或解析中)的解析任务。"""
    with _lock:
        for task in _tasks.values():
            if task.get("unit_id") != unit_id:
                continue
            if task.get("status") not in {"running", "queued"}:
                continue
            entry = next((m for m in task.get("materials") or [] if m.get("id") == material_id), None)
            if entry and entry.get("status") in {"pending", "parsing"}:
                return True
        return False


def _safe_subpath(root: Path, relative: str) -> Path:
    """将来源相对路径约束在 root 内, 防路径穿越。"""
    resolved = (root / relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in resolved.parents and resolved != root_resolved:
        raise ValueError("来源路径越界")
    return resolved


def _run_one(settings: Any, archive: dict, material: dict, engine: str, task_id: str, material_id: str, save_archive_fn) -> None:
    """在线程池中解析单个材料; 更新内存任务态 + 档案 JSON。"""
    try:
        update = lambda **kw: _update_task(task_id, material_id, **kw)  # noqa: E731
        update(status="parsing", progress=10, message="开始解析")
        # progress_cb: MinerU 子进程 tqdm 阶段进度 → 任务态 (0-100 + 阶段文案)
        def progress_cb(percent: int, message: str) -> None:
            update(status="parsing", progress=max(10, min(99, percent)), message=message)
        # 复用 course_archives 的解析逻辑（含本地来源读取、persist_original、缓存跳过）
        # select_engine: task 的 engine 决定用哪个解析引擎（rapidocr/mineru）;
        # force=True 会重新解析（即使已 parsed），用于"重新识别并保存"。
        updated = extract_course_archive_materials(
            archive, [material_id], settings.document_store_path, engine=engine, force=True,
            progress_cb=progress_cb,
        )
        # 解析完成后把 archive 回写磁盘: updated 是 archive 的 dict(extract 内部修改 materials/_documents)
        if save_archive_fn:
            save_archive_fn(updated)
        doc = updated.get("_documents", {}).get(material_id, {})
        update(status="parsed", progress=100, message=doc.get("engine") or "已提取")
    except Exception as exc:  # noqa: BLE001
        update(status="failed", progress=100, message=str(exc)[:240])


def _update_task(task_id: str, material_id: str, **changes: Any) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        entry = next((m for m in task["materials"] if m["id"] == material_id), None)
        if entry:
            entry.update(changes)
        task["progress"] = sum(m.get("progress", 0) for m in task["materials"]) / max(len(task["materials"]), 1)


def start_parse_task(settings: Any, archive: dict, material_ids: list[str], engine: str, save_archive_fn, unit_id: str = "") -> str:
    """并发2 后台解析。返回 task_id。

    unit_id 用于防重发: 同文件有未完成任务时调用方应拒绝(由 router 的 has_running_task
    前置判断), 这里仅记录以便查询。
    """
    task_id = f"parse-{__import__('uuid').uuid4().hex[:12]}"
    materials = {m["id"]: m for m in archive.get("materials", [])}
    with _lock:
        _tasks[task_id] = {
            "id": task_id,
            "unit_id": unit_id,
            "status": "running",
            "progress": 0,
            "engine": engine,
            "materials": [
                {"id": mid, "name": materials.get(mid, {}).get("name", mid),
                 "status": "pending",
                 "progress": 0, "message": ""}
                for mid in material_ids
            ],
            "errors": [],
        }

    def _worker_material(mid: str) -> None:
        try:
            mat = materials.get(mid, {})
            # force=True 无论如何都重新解析（"重新识别并保存"语义）
            _run_one(settings, archive, mat, engine, task_id, mid, save_archive_fn)
        except Exception as exc:  # noqa: BLE001
            _update_task(task_id, mid, status="failed", progress=100, message=str(exc)[:240])

    # 提交到线程池并发执行（受 _MAX_WORKERS=2 限制）
    for mid in material_ids:
        _pool.submit(_worker_material, mid)
    return task_id


def get_parse_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return None
        return {
            **task,
            "status": "completed" if task["status"] == "running" and task["progress"] >= 100 else task["status"],
            "materials": [dict(m) for m in task["materials"]],
        }
