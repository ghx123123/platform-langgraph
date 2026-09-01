import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from backend.core.config import get_settings
from backend.course_archives.service import _parse_uploaded, extract_course_archive_materials
from backend.course_archives.storage import load_archive, save_archive
from backend.course_archives.storage import list_archives
from backend.material_units.models import (
    KnowledgeOutline, KnowledgeOutlineCreate, KnowledgeOutlineList, KnowledgeOutlineRefineRequest,
    KnowledgeOutlineRefineTask, KnowledgeOutlineRefineTaskList, KnowledgeOutlineUpdate,
    MaterialUnitAppend, MaterialUnitCreate, MaterialUnitFileReferenceRequest, MaterialUnitImportPrecheckItem,
    MaterialUnitImportPrecheckRequest, MaterialUnitImportPrecheckResponse, MaterialUnitList, MaterialUnitMergeRequest,
    MaterialUnitRecord, MaterialUnitInitialOutline, MaterialUnitOutlineSave, MaterialUnitReferenceRequest,
    MaterialUnitRename, MaterialUnitScopeOptions, MaterialUnitScopeRequest, MaterialUnitSummary,
    SyllabusMatchRequest, SyllabusMatchResponse,
)
from backend.material_units.service import (
    SYLLABUS_CATEGORY_LABELS, accessible_material_documents, build_file_references, build_initial_outline,
    build_link, build_material_unit_file, build_refined_outline, build_scope_options, build_synthesize_context, create_knowledge_outline,
    create_or_update_material_unit, match_syllabus_requirements, material_unit_summary,
    merge_material_units, next_outline_version, refinement_evidence, restructure_outline, utc_now,
)
from backend.material_units.storage import (
    delete_material_unit, list_material_units, list_refine_tasks, load_material_unit, load_refine_task,
    save_material_unit, save_refine_task, save_graph_note, load_graph_note, delete_graph_note,
)
from backend.course_designs.storage import list_designs
import backend.material_units.parse_tasks as parse_tasks
from backend.workflows.dsh_engine import DshAgentEngine, DshEngineError


router = APIRouter(prefix="/api/material-units", tags=["material-units"])
_mutation_lock = asyncio.Lock()
_running_refine_tasks: set[str] = set()


def _creates_reference_cycle(target_id: str, source_id: str, records: dict[str, dict]) -> bool:
    pending = [source_id]
    visited: set[str] = set()
    while pending:
        current_id = pending.pop()
        if current_id == target_id:
            return True
        if current_id in visited:
            continue
        visited.add(current_id)
        current = records.get(current_id) or {}
        pending.extend(
            item.get("unit_id") for item in current.get("linked_units") or []
            if item.get("unit_id") and item.get("unit_id") not in visited
        )
    return False


@router.get("", response_model=MaterialUnitList)
async def material_units(archive_id: str = "") -> MaterialUnitList:
    settings = get_settings()
    records = await run_in_threadpool(list_material_units, settings.material_unit_store_path)
    if archive_id:
        records = [record for record in records if record.get("archive_id") == archive_id]
    return MaterialUnitList(items=[MaterialUnitSummary.model_validate(material_unit_summary(item)) for item in records])


async def _unit_with_links(unit_id: str) -> tuple[dict, list[dict], list[dict]]:
    settings = get_settings()
    try:
        record = await run_in_threadpool(load_material_unit, settings.material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc
    records = await run_in_threadpool(list_material_units, settings.material_unit_store_path)
    linked_ids = {item.get("unit_id") for item in record.get("linked_units") or []}
    live_map = {item.get("id"): item for item in records}
    linked = [live_map.get(item.get("unit_id")) or {
        "id": item.get("unit_id"), "title": item.get("title"), "archive_id": item.get("archive_id"),
        "archive_name": item.get("archive_name"), "material_count": item.get("material_count", 0),
        "files": item.get("files") or [], "material_ids": [file.get("material_id") for file in item.get("files") or []],
    } for item in record.get("linked_units") or [] if item.get("unit_id") in linked_ids]
    archives = await run_in_threadpool(list_archives, settings.course_archive_store_path)
    return record, linked, archives


async def _scope_context(unit_id: str) -> tuple[dict, list[dict], dict[str, dict], dict]:
    record, linked, archives_raw = await _unit_with_links(unit_id)
    archive_ids = {
        record.get("archive_id"),
        *[item.get("archive_id") for item in linked],
        *[item.get("archive_id") for item in record.get("material_references") or []],
    }
    archive_ids.discard(None)
    archives = {
        item["id"]: await run_in_threadpool(load_archive, get_settings().course_archive_store_path, item["id"])
        for item in archives_raw if item.get("id") in archive_ids
    }
    options = build_scope_options(record, linked, archives)
    return record, linked, archives, options


@router.get("/{unit_id}", response_model=MaterialUnitRecord)
async def material_unit(unit_id: str) -> MaterialUnitRecord:
    record, linked, archives_raw = await _unit_with_links(unit_id)
    record["linked_units"] = [build_link(item) for item in linked]
    record["linked_unit_count"] = len(record["linked_units"])
    # S5: files 从 archive 实时重建 (后台解析结果立刻反映, 而不是用存储时的 metadata_only 快照)
    archive = None
    if record.get("archive_id"):
        for item in archives_raw:
            if item.get("id") == record["archive_id"]:
                archive = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, item["id"])
                break
    if archive:
        known = {m["id"]: m for m in archive.get("materials", [])}
        docs = archive.get("_documents", {})
        ordered = list(dict.fromkeys(record.get("material_ids") or []))
        if ordered:
            rebuilt = []
            missing_ids = []
            for mid in ordered:
                if mid in known:
                    rebuilt.append(build_material_unit_file(known[mid], docs.get(mid)))
                else:
                    missing_ids.append(mid)
            record["files"] = rebuilt
            # 档案中已消失的材料: 不静默丢弃 — 记录数量差并在 overview 提示教师处理
            if missing_ids:
                record["material_count"] = len(ordered)
                record["overview"] = (
                    f"本单元登记 {len(ordered)} 份资料，其中 {len(missing_ids)} 份已不在课程资料库中（可能源文件被移除），"
                    f"显示 {len(rebuilt)} 份。可在资料库重新关联或从单元移除失效资料。"
                )
            parsed = [f for f in record["files"] if f["parse_status"] == "parsed"]
            record["parsed_count"] = len(parsed)
            record["overview"] = f"本单元包含 {len(record['files'])} 份资料，已完成 {len(parsed)} 份内容提取。"
    return MaterialUnitRecord.model_validate(record)


@router.get("/{unit_id}/scope-options", response_model=MaterialUnitScopeOptions)
async def scope_options(unit_id: str) -> MaterialUnitScopeOptions:
    _, _, _, options = await _scope_context(unit_id)
    return MaterialUnitScopeOptions.model_validate(options)


async def _model_syllabus_matches(request: Request, options: dict, teaching_item_ids: list[str]) -> list[dict]:
    workflow_service = getattr(request.app.state, "workflow_service", None)
    model = getattr(workflow_service, "model", None)
    if model is None or not hasattr(model, "generate_json"):
        return []
    teaching_map = {item["id"]: item for item in options.get("teaching_items") or []}
    selected = [teaching_map[item_id] for item_id in teaching_item_ids if item_id in teaching_map]
    candidates = [{
        "id": item["id"], "title": item.get("title", ""), "content": item.get("content", "")[:600],
    } for item in options.get("syllabus_items") or []]
    system_prompt = (
        "你是教学文档范围匹配器。只能在提供的大纲候选中判断与已选讲次相关的条目，不得新增或改写大纲要求。"
        "返回 JSON 对象，格式为 {\"matches\":[{\"id\":候选ID,\"category\":分类,\"score\":0到1,\"reason\":简短理由}]}。"
        f"分类只允许：{','.join(SYLLABUS_CATEGORY_LABELS)}。不相关条目不要返回。"
    )
    user_prompt = json.dumps({"selected_sessions": selected, "syllabus_candidates": candidates}, ensure_ascii=False)
    try:
        result = await model.generate_json(system_prompt, user_prompt)
    except Exception:
        return []
    known_ids = {item["id"] for item in candidates}
    return [
        item for item in result.get("matches", [])
        if isinstance(item, dict) and item.get("id") in known_ids
    ]


@router.post("/{unit_id}/syllabus-matches", response_model=SyllabusMatchResponse)
async def syllabus_matches(unit_id: str, payload: SyllabusMatchRequest, request: Request) -> SyllabusMatchResponse:
    _, _, _, options = await _scope_context(unit_id)
    model_matches = await _model_syllabus_matches(request, options, payload.teaching_item_ids) if payload.use_model else []
    try:
        result = match_syllabus_requirements(
            options, payload.teaching_item_ids, payload.limit_per_category, model_matches,
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SyllabusMatchResponse.model_validate(result)


@router.post("/{unit_id}/initial-outline", response_model=MaterialUnitInitialOutline)
async def initial_outline(unit_id: str, payload: MaterialUnitScopeRequest) -> MaterialUnitInitialOutline:
    options = await scope_options(unit_id)
    return MaterialUnitInitialOutline.model_validate(build_initial_outline(options.model_dump(), payload.model_dump()))


@router.put("/{unit_id}/initial-outline", response_model=MaterialUnitRecord)
async def save_initial_outline(unit_id: str, payload: MaterialUnitOutlineSave) -> MaterialUnitRecord:
    async with _mutation_lock:
        try:
            record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到资料单元") from exc
        record["initial_outline"] = payload.outline.model_dump()
        record["scope_selection"] = payload.scope_selection.model_dump()
        from backend.material_units.service import utc_now
        record["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)
        return MaterialUnitRecord.model_validate(record)


def _outline_versions(record: dict, outline_id: str) -> list[dict]:
    return sorted(
        [item for item in record.get("knowledge_outlines") or [] if item.get("id") == outline_id],
        key=lambda item: int(item.get("version") or 0),
    )


def _outline_version(record: dict, outline_id: str, version: int | None = None) -> dict:
    versions = _outline_versions(record, outline_id)
    if version is not None:
        versions = [item for item in versions if int(item.get("version") or 0) == version]
    if not versions:
        raise KeyError("未找到知识大纲版本")
    return versions[-1]


def _elapsed_seconds(task: dict) -> int:
    started = task.get("started_at") or task.get("created_at")
    finished = task.get("finished_at")
    if not started:
        return 0
    try:
        start_time = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(str(finished).replace("Z", "+00:00")) if finished else datetime.now(timezone.utc)
        return max(0, int((end_time - start_time).total_seconds()))
    except ValueError:
        return int(task.get("elapsed_seconds") or 0)


def _public_task(task: dict) -> KnowledgeOutlineRefineTask:
    return KnowledgeOutlineRefineTask.model_validate({**task, "elapsed_seconds": _elapsed_seconds(task)})


async def _update_refine_task(task: dict, **changes: object) -> dict:
    task.update(changes)
    task["updated_at"] = utc_now()
    task["elapsed_seconds"] = _elapsed_seconds(task)
    await run_in_threadpool(save_refine_task, get_settings().material_unit_store_path, task)
    return task


async def _run_refine_task(task_id: str, request: Request) -> None:
    if task_id in _running_refine_tasks:
        return
    _running_refine_tasks.add(task_id)
    settings = get_settings()
    try:
        task = await run_in_threadpool(load_refine_task, settings.material_unit_store_path, task_id)
        if task.get("status") in {"completed", "failed"}:
            return
        await _update_refine_task(
            task, status="loading_sources", progress=18, started_at=task.get("started_at") or utc_now(),
            stage_label="正在读取所选资料和已保存的大纲版本",
        )
        record, linked, archives, _ = await _scope_context(task["unit_id"])
        latest = _outline_version(record, task["outline_id"])
        if int(latest["version"]) != int(task["base_version"]):
            raise RuntimeError("知识大纲已产生新版本，请重新发起细化")
        accessible = accessible_material_documents(record, linked, archives)
        missing_ids = [item_id for item_id in task["material_ids"] if item_id not in accessible]
        if missing_ids:
            raise RuntimeError(f"所选资料已不可用：{', '.join(missing_ids)}")
        await _update_refine_task(
            task, status="analyzing", progress=38,
            stage_label=f"正在分析 {len(task['material_ids'])} 份资料的章节与证据",
        )
        await _update_refine_task(
            task, status="generating", progress=62,
            stage_label="智能体正在生成有原文依据的细化知识点" if task.get("use_model", True) else "正在按原文证据生成细化知识点",
        )
        model_nodes = await _model_refined_nodes(
            request, latest, task["material_ids"], task["teacher_instruction"], accessible,
        ) if task.get("use_model", True) else []
        version = build_refined_outline(
            latest, task["material_ids"], task["teacher_instruction"], accessible, model_nodes,
        )
        validated = KnowledgeOutline.model_validate(version).model_dump()
        await _update_refine_task(task, status="saving", progress=88, stage_label="正在保存新版本和来源证据")
        async with _mutation_lock:
            current = await run_in_threadpool(load_material_unit, settings.material_unit_store_path, task["unit_id"])
            current_latest = _outline_version(current, task["outline_id"])
            if int(current_latest["version"]) != int(task["base_version"]):
                raise RuntimeError("保存前检测到知识大纲已更新，本次结果未覆盖新版本")
            current["knowledge_outlines"] = [*(current.get("knowledge_outlines") or []), validated]
            current["updated_at"] = utc_now()
            await run_in_threadpool(save_material_unit, settings.material_unit_store_path, current)
        await _update_refine_task(
            task, status="completed", progress=100, result_version=validated["version"],
            stage_label=f"细化完成，已保存为第 {validated['version']} 版", finished_at=utc_now(),
        )
    except Exception as exc:
        try:
            task = await run_in_threadpool(load_refine_task, settings.material_unit_store_path, task_id)
            await _update_refine_task(
                task, status="failed", progress=min(int(task.get("progress") or 0), 95),
                stage_label="细化任务未完成", error=str(exc), finished_at=utc_now(),
            )
        except Exception:
            pass
    finally:
        _running_refine_tasks.discard(task_id)


@router.post(
    "/{unit_id}/knowledge-outlines/{outline_id}/refine-tasks",
    response_model=KnowledgeOutlineRefineTask,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_refine_task(
    unit_id: str,
    outline_id: str,
    payload: KnowledgeOutlineRefineRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> KnowledgeOutlineRefineTask:
    try:
        record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        latest = _outline_version(record, outline_id)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail="未找到知识大纲版本") from exc
    base_version = payload.base_version or int(latest["version"])
    if base_version != int(latest["version"]):
        raise HTTPException(status_code=409, detail="知识大纲已更新，请刷新后再细化")
    existing = await run_in_threadpool(
        list_refine_tasks, get_settings().material_unit_store_path, unit_id, outline_id,
    )
    if any(item.get("status") not in {"completed", "failed"} for item in existing):
        raise HTTPException(status_code=409, detail="该知识大纲已有细化任务正在运行")
    timestamp = utc_now()
    task = KnowledgeOutlineRefineTask(
        id=str(uuid4()), unit_id=unit_id, outline_id=outline_id, base_version=base_version,
        material_ids=payload.material_ids, teacher_instruction=payload.teacher_instruction,
        use_model=payload.use_model, created_at=timestamp, updated_at=timestamp,
        progress=5, stage_label="任务已保存，等待开始分析",
    ).model_dump()
    await run_in_threadpool(save_refine_task, get_settings().material_unit_store_path, task)
    background_tasks.add_task(_run_refine_task, task["id"], request)
    return _public_task(task)


@router.get(
    "/{unit_id}/knowledge-outlines/{outline_id}/refine-tasks",
    response_model=KnowledgeOutlineRefineTaskList,
)
async def refine_tasks(
    unit_id: str,
    outline_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> KnowledgeOutlineRefineTaskList:
    tasks = await run_in_threadpool(
        list_refine_tasks, get_settings().material_unit_store_path, unit_id, outline_id,
    )
    for task in tasks:
        if task.get("status") not in {"completed", "failed"} and task["id"] not in _running_refine_tasks:
            background_tasks.add_task(_run_refine_task, task["id"], request)
    return KnowledgeOutlineRefineTaskList(items=[_public_task(item) for item in tasks])


@router.get(
    "/{unit_id}/knowledge-outlines/{outline_id}/refine-tasks/{task_id}",
    response_model=KnowledgeOutlineRefineTask,
)
async def refine_task(unit_id: str, outline_id: str, task_id: str) -> KnowledgeOutlineRefineTask:
    try:
        task = await run_in_threadpool(load_refine_task, get_settings().material_unit_store_path, task_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到知识大纲细化任务") from exc
    if task.get("unit_id") != unit_id or task.get("outline_id") != outline_id:
        raise HTTPException(status_code=404, detail="未找到知识大纲细化任务")
    return _public_task(task)


@router.post("/{unit_id}/knowledge-outlines", response_model=KnowledgeOutline, status_code=201)
async def create_outline(unit_id: str, payload: KnowledgeOutlineCreate) -> KnowledgeOutline:
    async with _mutation_lock:
        record, _, _, options = await _scope_context(unit_id)
        try:
            matching = match_syllabus_requirements(options, payload.teaching_item_ids, limit_per_category=8)
            outline = create_knowledge_outline(unit_id, options, payload.model_dump(), matching["matches"])
            validated = KnowledgeOutline.model_validate(outline).model_dump()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        record["knowledge_outlines"] = [*(record.get("knowledge_outlines") or []), validated]
        record["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)
        return KnowledgeOutline.model_validate(validated)


@router.get("/{unit_id}/knowledge-outlines", response_model=KnowledgeOutlineList)
async def list_outlines(unit_id: str, include_versions: bool = False) -> KnowledgeOutlineList:
    try:
        record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc
    outlines = record.get("knowledge_outlines") or []
    if not include_versions:
        latest: dict[str, dict] = {}
        for outline in outlines:
            current = latest.get(outline.get("id"))
            if current is None or int(outline.get("version") or 0) > int(current.get("version") or 0):
                latest[outline.get("id")] = outline
        outlines = list(latest.values())
    outlines = sorted(
        outlines,
        key=lambda item: (str(item.get("id") or ""), int(item.get("version") or 0)),
        reverse=True,
    )
    return KnowledgeOutlineList(items=[KnowledgeOutline.model_validate(item) for item in outlines])


@router.get("/{unit_id}/knowledge-outlines/{outline_id}", response_model=KnowledgeOutline)
async def read_outline(
    unit_id: str,
    outline_id: str,
    version: int | None = Query(default=None, ge=1),
) -> KnowledgeOutline:
    try:
        record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        return KnowledgeOutline.model_validate(_outline_version(record, outline_id, version))
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail="未找到知识大纲版本") from exc


@router.delete("/{unit_id}/knowledge-outlines/{outline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outline_version(
    unit_id: str,
    outline_id: str,
    version: int | None = Query(default=None, ge=1),
    all_history: bool = False,
) -> Response:
    async with _mutation_lock:
        try:
            record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
            versions = _outline_versions(record, outline_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到资料单元") from exc
        if not versions:
            raise HTTPException(status_code=404, detail="未找到知识大纲")
        selected_version = version if version is not None else int(versions[-1]["version"])
        if not all_history and not any(int(item["version"]) == selected_version for item in versions):
            raise HTTPException(status_code=404, detail="未找到知识大纲版本")
        tasks = await run_in_threadpool(
            list_refine_tasks, get_settings().material_unit_store_path, unit_id, outline_id,
        )
        if any(item.get("status") not in {"completed", "failed"} for item in tasks):
            raise HTTPException(status_code=409, detail="该知识大纲正在细化，请等待任务完成后再删除")
        designs = await run_in_threadpool(list_designs, get_settings().course_design_store_path)
        references = [
            item for item in designs
            if item.get("material_unit_id") == unit_id
            and item.get("knowledge_outline_id") == outline_id
            and (all_history or int(item.get("knowledge_outline_version") or 0) == selected_version)
        ]
        if references:
            titles = "、".join(str(item.get("title") or "未命名课程设计") for item in references[:3])
            raise HTTPException(status_code=409, detail=f"该版本正在被课程设计引用：{titles}。请先删除或更换课程设计引用。")
        if all_history:
            remaining = [item for item in record.get("knowledge_outlines") or [] if item.get("id") != outline_id]
        else:
            remaining = [
                item for item in record.get("knowledge_outlines") or []
                if not (item.get("id") == outline_id and int(item.get("version") or 0) == selected_version)
            ]
        record["knowledge_outlines"] = remaining
        record["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{unit_id}/knowledge-outlines/{outline_id}", response_model=KnowledgeOutline)
async def update_outline(unit_id: str, outline_id: str, payload: KnowledgeOutlineUpdate) -> KnowledgeOutline:
    async with _mutation_lock:
        try:
            record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
            base = _outline_version(record, outline_id)
            if payload.base_version != base["version"]:
                raise HTTPException(status_code=409, detail="知识大纲已更新，请刷新后再编辑")
            version = KnowledgeOutline.model_validate(next_outline_version(base, payload.model_dump())).model_dump()
        except HTTPException:
            raise
        except (FileNotFoundError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=404 if isinstance(exc, (FileNotFoundError, KeyError)) else 422, detail=str(exc)) from exc
        record["knowledge_outlines"] = [*(record.get("knowledge_outlines") or []), version]
        record["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)
        return KnowledgeOutline.model_validate(version)


async def _model_refined_nodes(
    request: Request,
    base: dict,
    material_ids: list[str],
    teacher_instruction: str,
    accessible: dict[str, dict],
) -> list[dict]:
    workflow_service = getattr(request.app.state, "workflow_service", None)
    model = getattr(workflow_service, "model", None)
    if model is None or not hasattr(model, "generate_json"):
        return []
    evidence = [{key: value for key, value in item.items() if key != "source"} for item in refinement_evidence(base, material_ids, accessible)]
    # S2: 无材料(material_ids 为空但 teacher_instruction 非空)时, 进入"自由扩展模式":
    # 不要求 evidence, 允许基于 instruction 为现有知识点添加下级节点
    free_instruction_mode = not material_ids and bool(teacher_instruction.strip())
    if free_instruction_mode:
        # M6+: AI 优化 → 完整重构模式: 模型直接返回重构后的 nodes 数组(合并/重排/拆分直接用 nodes 表达)
        system_prompt = (
            "你是知识大纲重构器。教师可能要求对现有大纲做结构级修改：合并/拆分知识点、调整层级、"
            "重排顺序、改标题、修改或补充说明文字。请按教师指令重构整个大纲。\n"
            "约束：\n"
            "1. 只能重构当前大纲已有的知识点，不得引入与教师指令无关的新知识点；\n"
            "2. 每个节点必须保留或适配原节点内容：合并节点时合并两个原节点的说明，拆分时按逻辑成 2 个；\n"
            "3. level 取 1-3，层级需合理；新增节点必须挂在现有节点之下；\n"
            "4. 若教师指令包含原文提示词/教材引用，可生成对应的新节点，但不要编造教材没有的内容；\n"
            "5. 不要输出讲解顺序/教学活动/课堂流程，只整理知识结构。\n"
            "返回 {\"nodes\":[{\"title\":\"...\",\"description\":\"...\",\"level\":1到3,"
            "\"parent_id\":null|父节点title,\"is_key_point\":bool,\"is_difficult_point\":bool}]}。"
            "parent_id 引用同批次节点的 title；无父节点的 1 级节点用 null。"
        )
        user_prompt = json.dumps({
            "current_scope": [{"id": item.get("id"), "title": item.get("title"), "description": item.get("description", "")} for item in base.get("nodes", [])],
            "teacher_instruction": teacher_instruction,
            "mode": "restructure",
            "free_instruction_mode": True,
        }, ensure_ascii=False)
        try:
            result = await model.generate_json(system_prompt, user_prompt)
        except Exception:
            return []
        nodes = result.get("nodes") if isinstance(result.get("nodes"), list) else result.get("changes", [])
        return [item for item in nodes if isinstance(item, dict)]
    system_prompt = (
        "你是知识大纲细化器。教师已经确认 current_scope，它是不可突破的硬边界。"
        "你只能细化这些现有知识点，不得加入未选择的章节、节、主题或把整份资料目录搬入大纲。"
        "默认使用 update 完善现有知识点的 description，不改标题、不新增节点。"
        "只有 expansion_allowed=true 时才可使用 add，且新增项必须是现有知识点的下级内容。"
        "update 必须填写 node_id；add 必须填写所属现有知识点 parent_node_id。"
        "每项只能引用 allowed_parent_ids 包含对应现有节点ID的 evidence id。"
        "如果证据不属于现有范围，必须忽略；没有合格证据时返回空 nodes。最多返回 6 个节点。"
        "自由扩展模式(无材料证据时)：教师提供了补充说明, 允许基于补充说明在现有知识点下新增下级节点, "
        "evidence_ids 可以为空。不得修改现有节点。"
        "只整理知识点，不设计教学活动、讲解顺序或课堂流程。"
        "返回 {\"changes\":[{\"operation\":\"update\"或\"add\",\"node_id\":现有节点ID,"
        "\"parent_node_id\":现有节点ID,\"title\":...,\"description\":...,\"level\":2到3,"
        "\"is_key_point\":false,\"is_difficult_point\":false,\"evidence_ids\":[...]}]}。"
    )
    user_prompt = json.dumps({
        "current_scope": [{"id": item.get("id"), "title": item.get("title"), "description": item.get("description", "")} for item in base.get("nodes", [])],
        "teacher_instruction": teacher_instruction,
        "expansion_allowed": bool(re.search(r"新增|增加|补充|拆分|扩展|子知识点|下级知识点", teacher_instruction)),
        "evidence": evidence,
        "free_instruction_mode": free_instruction_mode,
    }, ensure_ascii=False)
    try:
        result = await model.generate_json(system_prompt, user_prompt)
    except Exception:
        return []
    changes = result.get("changes") if isinstance(result.get("changes"), list) else result.get("nodes", [])
    return [item for item in changes if isinstance(item, dict)]


@router.post("/{unit_id}/knowledge-outlines/{outline_id}/refine", response_model=KnowledgeOutline)
async def refine_outline(
    unit_id: str,
    outline_id: str,
    payload: KnowledgeOutlineRefineRequest,
    request: Request,
) -> KnowledgeOutline:
    async with _mutation_lock:
        record, linked, archives, _ = await _scope_context(unit_id)
        try:
            latest = _outline_version(record, outline_id)
            if payload.base_version is not None and payload.base_version != latest["version"]:
                raise HTTPException(status_code=409, detail="知识大纲已更新，请刷新后再细化")
            base = latest
            accessible = accessible_material_documents(record, linked, archives)
            model_nodes = await _model_refined_nodes(
                request, base, payload.material_ids, payload.teacher_instruction, accessible,
            ) if payload.use_model else []
            if not payload.material_ids:
                # M6+: AI 优化(无材料) → 完整重构模式(合并/重排/拆分由模型直接输出 nodes)
                version = restructure_outline(base, payload.teacher_instruction, model_nodes)
            else:
                version = build_refined_outline(
                    base, payload.material_ids, payload.teacher_instruction, accessible, model_nodes,
                )
            validated = KnowledgeOutline.model_validate(version).model_dump()
        except HTTPException:
            raise
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        record["knowledge_outlines"] = [*(record.get("knowledge_outlines") or []), validated]
        record["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)
        return KnowledgeOutline.model_validate(validated)


# ---------- P3: 大纲整合模式 (LLM 概括, 支持 无材料/仅提示词) ----------
@router.post("/{unit_id}/knowledge-outlines/synthesize", response_model=KnowledgeOutline, status_code=201)
async def synthesize_outline(
    unit_id: str,
    payload: KnowledgeOutlineRefineRequest,
    request: Request,
) -> KnowledgeOutline:
    """整合模式: 有材料 → LLM 依据材料摘要整合; 无材料 → 仅依据 teacher_instruction 生成连贯大纲。"""
    workflow_service = getattr(request.app.state, "workflow_service", None)
    model = getattr(workflow_service, "model", None)
    if model is None or not hasattr(model, "generate_json"):
        raise HTTPException(status_code=422, detail="当前模型不可用, 无法整合大纲")
    async with _mutation_lock:
        record, linked, archives, options = await _scope_context(unit_id)
        accessible = accessible_material_documents(record, linked, archives)
        ctx = build_synthesize_context(options, payload.model_dump(), accessible)
        if ctx["mode"] == "empty":
            raise HTTPException(status_code=422, detail="请选择教材章节/大纲要求, 或提供教师明确补充说明")
        system_prompt = (
            "你是知识大纲整合器。教师已确定教学范围(讲次/大纲要求/教材章节/教师补充说明)。"
            "请把以下资料整合为一份**连贯的教学知识大纲**, 不是简单罗列目录: "
            "合并重复概念, 按知识逻辑组织为 level 1(章节主题)-2(知识点)-3(下级知识点) 层级; "
            "每个节点写简短 description(含义/学什么); 标注 is_key_point(重点) 与 is_difficult_point(难点); "
            "不擅自引入与资料无关的新主题(除非教师补充说明明确要求)。最多 30 个节点。"
            "返回 {\"nodes\":[{\"title\":...,\"description\":...,\"level\":1到3,\"parent_id\":null|父节点title,"
            "\"is_key_point\":bool,\"is_difficult_point\":bool}]}。parent_id 用于建立层级(引用同批节点的 title)。"
        )
        user_prompt = json.dumps({
            "session": ctx["session"], "objective": ctx["objective"],
            "sections": ctx["sections"], "material_excerpts": ctx["material_excerpts"],
            "teacher_instruction": ctx["teacher_instruction"],
            "mode": ctx["mode"],
        }, ensure_ascii=False)
        try:
            result = await model.generate_json(system_prompt, user_prompt)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="LLM 整合失败: " + str(exc)[:200]) from exc
        nodes = [item for item in (result.get("nodes") or []) if isinstance(item, dict) and item.get("title")]
        if not nodes:
            raise HTTPException(status_code=422, detail="模型未产出有效节点")
        by_title = {node.get("title", ""): str(uuid4()) for node in nodes}
        imported_nodes = []
        for node in nodes:
            title = str(node.get("title", ""))[:240]
            parent_title = node.get("parent_id") if node.get("parent_id") else None
            imported_nodes.append({
                "id": by_title.get(title, str(uuid4())),
                "parent_id": by_title.get(str(parent_title)) if parent_title else None,
                "level": int(node.get("level") or 1),
                "title": title,
                "description": str(node.get("description") or "")[:2000],
                "is_key_point": bool(node.get("is_key_point") or False),
                "is_difficult_point": bool(node.get("is_difficult_point") or False),
                "teacher_note": "",
                "evidence": [{"source_type": "teacher", "quote": (payload.teacher_instruction or "")[:2000], "label": "整合模式"}],
            })
        now = utc_now()
        outline = {
            "id": str(uuid4()), "unit_id": unit_id, "version": 1, "status": "draft",
            "title": ctx["title"],
            "selected_session_ids": [], "selected_syllabus_item_ids": [], "selected_textbook_node_ids": [],
            "requirements": [], "nodes": imported_nodes,
            "source_material_ids": [], "teacher_instruction": payload.teacher_instruction or "",
            "change_summary": "整合模式生成", "based_on_version": None,
            "created_at": now, "updated_at": now,
        }
        validated = KnowledgeOutline.model_validate(outline).model_dump()
        record["knowledge_outlines"] = [*(record.get("knowledge_outlines") or []), validated]
        record["updated_at"] = now
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)
        return KnowledgeOutline.model_validate(validated)


async def _extract_and_build(archive_id: str, title: str, material_ids: list[str], existing: dict | None = None, extract_immediately: bool = False) -> dict:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        # S3: extract_immediately=False(默认) → 仅登记单元, 避免导入时慢在完整解析;
        #     完整正文提取推迟到"知识大纲"步骤(此时 accessible_material_documents 按需调 extract)
        if extract_immediately:
            archive = await run_in_threadpool(extract_course_archive_materials, archive, material_ids, settings.document_store_path)
            await run_in_threadpool(save_archive, settings.course_archive_store_path, archive)
        record = await run_in_threadpool(create_or_update_material_unit, archive, title, material_ids, existing)
        await run_in_threadpool(save_material_unit, settings.material_unit_store_path, record)
        return record
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到课程资料库") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", response_model=MaterialUnitRecord, status_code=201)
async def create_material_unit(payload: MaterialUnitCreate) -> MaterialUnitRecord:
    async with _mutation_lock:
        return MaterialUnitRecord.model_validate(await _extract_and_build(payload.archive_id, payload.title, payload.material_ids, extract_immediately=payload.extract_immediately))


@router.post("/{unit_id}/materials", response_model=MaterialUnitRecord)
async def append_material_unit(unit_id: str, payload: MaterialUnitAppend) -> MaterialUnitRecord:
    async with _mutation_lock:
        try:
            existing = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到资料单元") from exc
        return MaterialUnitRecord.model_validate(await _extract_and_build(existing["archive_id"], existing["title"], payload.material_ids, existing, extract_immediately=payload.extract_immediately))


@router.patch("/{unit_id}", response_model=MaterialUnitRecord)
async def rename_material_unit(unit_id: str, payload: MaterialUnitRename) -> MaterialUnitRecord:
    async with _mutation_lock:
        try:
            record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到资料单元") from exc
        record["title"] = payload.title.strip()
        from backend.material_units.service import utc_now
        record["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, record)
        return MaterialUnitRecord.model_validate(record)


@router.delete("/{unit_id}", status_code=204)
async def remove_material_unit(unit_id: str) -> None:
    try:
        await run_in_threadpool(delete_material_unit, get_settings().material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc


@router.post("/{unit_id}/references", response_model=MaterialUnitRecord)
async def reference_material_units(unit_id: str, payload: MaterialUnitReferenceRequest) -> MaterialUnitRecord:
    async with _mutation_lock:
        try:
            target = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到目标资料单元") from exc
        records = await run_in_threadpool(list_material_units, get_settings().material_unit_store_path)
        source_map = {item.get("id"): item for item in records}
        missing = [source_id for source_id in payload.unit_ids if source_id not in source_map or source_id == unit_id]
        if missing:
            raise HTTPException(status_code=422, detail="引用的资料单元不存在或不能引用自身")
        circular = [source_id for source_id in payload.unit_ids if _creates_reference_cycle(unit_id, source_id, source_map)]
        if circular:
            raise HTTPException(status_code=422, detail="不能建立循环引用，请保留单向资料关联")
        existing_ids = {item.get("unit_id") for item in target.get("linked_units") or []}
        target["linked_units"] = list(target.get("linked_units") or []) + [
            build_link(source_map[source_id]) for source_id in payload.unit_ids if source_id not in existing_ids
        ]
        target = merge_material_units(target, [])
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, target)
        return MaterialUnitRecord.model_validate(target)


@router.post("/{unit_id}/material-references", response_model=MaterialUnitRecord)
async def reference_material_files(unit_id: str, payload: MaterialUnitFileReferenceRequest) -> MaterialUnitRecord:
    async with _mutation_lock:
        try:
            target = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到目标资料单元") from exc
        records = await run_in_threadpool(list_material_units, get_settings().material_unit_store_path)
        source_map = {item.get("id"): item for item in records}
        source = source_map.get(payload.source_unit_id)
        if source is None or payload.source_unit_id == unit_id:
            raise HTTPException(status_code=422, detail="来源资料单元不存在或不能关联自身文件")
        existing = target.get("material_references") or []
        existing_keys = {(item.get("source_unit_id"), item.get("material_id")) for item in existing}
        try:
            additions = [
                item for item in build_file_references(source, payload.material_ids)
                if (item.get("source_unit_id"), item.get("material_id")) not in existing_keys
            ]
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        target["material_references"] = [*existing, *additions]
        target["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, target)
        return MaterialUnitRecord.model_validate(target)


@router.delete("/{unit_id}/material-references/{reference_id}", response_model=MaterialUnitRecord)
async def remove_material_file_reference(unit_id: str, reference_id: str) -> MaterialUnitRecord:
    async with _mutation_lock:
        try:
            target = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到目标资料单元") from exc
        existing = target.get("material_references") or []
        remaining = [item for item in existing if item.get("id") != reference_id]
        if len(remaining) == len(existing):
            raise HTTPException(status_code=404, detail="未找到文件关联")
        target["material_references"] = remaining
        target["updated_at"] = utc_now()
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, target)
        return MaterialUnitRecord.model_validate(target)


@router.post("/{unit_id}/merge", response_model=MaterialUnitRecord)
async def merge_units(unit_id: str, payload: MaterialUnitMergeRequest) -> MaterialUnitRecord:
    async with _mutation_lock:
        try:
            target = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到目标资料单元") from exc
        records = await run_in_threadpool(list_material_units, get_settings().material_unit_store_path)
        source_map = {item.get("id"): item for item in records}
        ids = list(dict.fromkeys(payload.source_unit_ids))
        if unit_id in ids or any(source_id not in source_map for source_id in ids):
            raise HTTPException(status_code=422, detail="合并来源中包含不存在的资料单元或目标单元自身")
        merged = merge_material_units(target, [source_map[source_id] for source_id in ids], payload.title)
        await run_in_threadpool(save_material_unit, get_settings().material_unit_store_path, merged)
        for source_id in ids:
            await run_in_threadpool(delete_material_unit, get_settings().material_unit_store_path, source_id)
        return MaterialUnitRecord.model_validate(merged)


# ---------- P1: 后台异步解析任务 (仅资料单元路径, 并发2) ----------
@router.post("/{unit_id}/import-precheck", response_model=MaterialUnitImportPrecheckResponse)
async def unit_import_precheck(unit_id: str, payload: MaterialUnitImportPrecheckRequest) -> MaterialUnitImportPrecheckResponse:
    """导入课程设计前的解析检查：报告每份材料的解析状态，标记需要先补齐解析的。

    只为"导入课程设计"复用解析成果服务——凡是未完整提取(metadata_only/parse_failed/unsupported)
    的材料都 needs_parse，前端据此先触发后台解析，完成后才真正 create 课程设计，避免二次解析。
    """
    settings = get_settings()
    try:
        record = await run_in_threadpool(load_material_unit, settings.material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc
    # 解析状态以档案为准(材料解析后写回 archive.materials.parse_status)，跨关联单元统一检查
    record, linked, archives, _ = await _scope_context(unit_id)
    accessible = accessible_material_documents(record, linked, archives)
    items: list[MaterialUnitImportPrecheckItem] = []
    for material_id in payload.material_ids:
        entry = accessible.get(material_id) or {}
        material = entry.get("material") or {}
        document = entry.get("document") or {}
        status = material.get("parse_status") or "metadata_only"
        has_raw = bool(document.get("raw_text"))
        # 只有"完整提取"才算可直接复用；其余(含 metadata_only/parse_failed/unsupported)都需先补齐解析
        needs_parse = status != "parsed" or not has_raw
        items.append(MaterialUnitImportPrecheckItem(
            material_id=material_id,
            name=material.get("name") or material_id,
            parse_status="parsed" if has_raw else status,
            parse_message=material.get("parse_message") or "",
            needs_parse=needs_parse,
        ))
    return MaterialUnitImportPrecheckResponse(
        all_parsed=not any(item.needs_parse for item in items),
        needs_parse=[item for item in items if item.needs_parse],
        items=items,
    )


@router.post("/{unit_id}/parse-tasks", status_code=202)
async def start_unit_parse(unit_id: str, payload: MaterialUnitAppend) -> dict:
    """后台解析 unit 关联的材料; 返回 task_id (立即), 进度用 GET 轮询。"""
    settings = get_settings()
    try:
        record = await run_in_threadpool(load_material_unit, settings.material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, record["archive_id"])
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到课程资料库") from exc

    def _save(updated: dict) -> None:
        # 在 parse 线程池内直接同步保存 (不能又进 run_in_threadpool, 可能嵌套死锁)
        save_archive(settings.course_archive_store_path, updated)

    async def _persist_now(updated: dict) -> None:
        await run_in_threadpool(save_archive, settings.course_archive_store_path, updated)

    # 防重发: 已在排队/解析中的文件不再重复发起, 返回 409 提示
    duplicate_ids = [mid for mid in payload.material_ids if parse_tasks.has_running_task(unit_id, mid)]
    if duplicate_ids:
        names = [m.get("name", mid) for mid in duplicate_ids for m in archive.get("materials", []) if m.get("id") == mid]
        raise HTTPException(status_code=409, detail=f"这些文件已有正在进行的识别任务: {'、'.join(names[:3])}")

    task_id = await run_in_threadpool(
        parse_tasks.start_parse_task,
        settings, archive, payload.material_ids, "mineru",
        _save, unit_id=unit_id,
    )
    return {"task_id": task_id, "status": "started", "engine": "mineru"}


@router.get("/{unit_id}/files/{material_id}/text")
async def unit_file_text(unit_id: str, material_id: str) -> dict:
    """返回单元内某份文件的识别后原文(raw_text), 供前端"识别结果 vs 原文档"对比展示。"""
    try:
        record = await run_in_threadpool(load_material_unit, get_settings().material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc
    archive = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, record.get("archive_id", ""))
    doc = archive.get("_documents", {}).get(material_id, {})
    raw = doc.get("raw_text", "")
    if not raw:
        # 可能在其他关联档案里
        for link in record.get("linked_units") or []:
            try:
                linked_archive = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, link.get("archive_id", ""))
                raw = linked_archive.get("_documents", {}).get(material_id, {}).get("raw_text", "")
                if raw: break
            except (FileNotFoundError, ValueError):
                continue
    if not raw:
        raise HTTPException(status_code=404, detail="该文件尚未提取正文，请在资料库中发起识别")
    # 页对齐: 用 page_offsets 把 raw_text 切为 带"【第N页】"标记的分段
    offsets = doc.get("page_offsets") or []
    pages = []
    if offsets:
        raw_text = doc.get("raw_text", "")
        for index, (start, end) in enumerate(offsets, start=1):
            pages.append({"page": index, "text": raw_text[max(0, start):min(end, len(raw_text))]})
    else:
        pages = [{"page": 1, "text": raw[:120000]}]
    return {"ok": True, "material_id": material_id, "character_count": len(raw), "text": raw[:120000], "pages": pages}


@router.get("/{unit_id}/parse-tasks/{task_id}")
async def unit_parse_status(unit_id: str, task_id: str) -> dict:
    """轮询解析任务进度: {status, progress, materials:[{id,name,status,progress,message}]}"""
    task = parse_tasks.get_parse_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="解析任务不存在")
    complete = all(item["status"] in ("parsed", "cached", "failed") for item in task["materials"])
    return {
        "task_id": task_id,
        "status": "completed" if complete else task["status"],
        "progress": task["progress"],
        "engine": task["engine"],
        "materials": task["materials"],
    }


@router.post("/{unit_id}/files/{material_id}/reparse")
async def unit_file_reparse(unit_id: str, material_id: str, payload: dict, request: Request) -> dict:
    """用指定引擎后台重新识别该文件并保存结果 (rapidocr 默认 / mineru)。

    与 start_unit_parse 相同: 返回 task_id 立即, 进度用 GET /parse-tasks/{task_id} 轮询。
    force=True 会让 extract 重解析该文件(跳过"已 parsed 则跳过"缓存)。
    """
    engine = str(payload.get("engine") or "mineru")
    settings = get_settings()
    try:
        record = await run_in_threadpool(load_material_unit, settings.material_unit_store_path, unit_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到资料单元") from exc
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, record.get("archive_id", ""))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到课程资料库") from exc
    materials = {m["id"]: m for m in archive.get("materials", [])}
    material = materials.get(material_id)
    if not material:
        raise HTTPException(status_code=404, detail="文件不存在")
    if parse_tasks.has_running_task(unit_id, material_id):
        raise HTTPException(status_code=409, detail="该文件已有正在进行的识别任务，请等待完成或刷新查看进度")
    if material.get("parse_status") == "parsed" and not material.get("document_id"):
        raise HTTPException(status_code=422, detail="该文件已有解析结果但缺少文档 ID，无法重识别")
    if material.get("character_count") and engine == material.get("extraction_engine"):
        # 已用同一引擎解析过, 跳过 (同步快路径)
        pass

    def _save(updated: dict) -> None:
        save_archive(settings.course_archive_store_path, updated)

    task_id = await run_in_threadpool(
        parse_tasks.start_parse_task,
        settings, archive, [material_id], engine,
        _save, unit_id=unit_id,
    )
    return {"task_id": task_id, "status": "started", "engine": engine}
    if not task:
        raise HTTPException(status_code=404, detail="解析任务不存在")
    complete = all(item["status"] in ("parsed", "cached", "failed") for item in task["materials"])
    return {
        "task_id": task_id,
        "status": "completed" if complete else task["status"],
        "progress": task["progress"],
        "engine": task["engine"],
        "materials": task["materials"],
    }
