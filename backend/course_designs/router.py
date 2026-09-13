import hashlib
import re
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from backend.core.config import get_settings
from backend.course_archives.storage import load_archive
from backend.course_designs.models import (
    CourseDesignAssemblyApply, CourseDesignAssemblySourceList, CourseDesignCreate,
    CourseDesignExportList, CourseDesignExportRecord, CourseDesignExportRequest,
    CourseDesignKnowledgeOutline, CourseDesignList, CourseDesignRecord, CourseDesignSummary,
    CourseDesignTemplateInspection, CourseDesignUpdate, CourseDesignVersionList, CourseReferenceDetail,
)
from backend.course_designs.service import (
    apply_assembly, assembly_sources, build_docx, create_design, inspect_docx_template,
    CrossArchiveReferenceError, public_record, rebind_design, reference_detail, restore_source_snapshot, summary, sync_run,
    update_design, utc_now, validate_run_context, _pending_content_fields,
    review_blockers,
)
from backend.course_designs.storage import delete_design, list_designs, load_design, save_design
from backend.documents.storage import delete_document, original_path, persist_original
from backend.material_units.storage import load_material_unit


router = APIRouter(prefix="/api/course-designs", tags=["course-designs"])


async def _attach_outline_status(record: dict) -> dict:
    """填充大纲版本状态：outline_has_newer_version / outline_latest_version。

    课程设计引用某大纲版本(快照)，若该大纲之后又产生了新版本，则标记有更新，
    前端据此显示「📌 大纲已更新至 vN」徽标 + 一键升级按钮。不写库，仅响应时计算。
    """
    record["outline_has_newer_version"] = False
    record["outline_latest_version"] = None
    if not record.get("knowledge_outline_id") or not record.get("material_unit_id"):
        return record
    try:
        unit = await run_in_threadpool(
            load_material_unit, get_settings().material_unit_store_path, record["material_unit_id"]
        )
    except (FileNotFoundError, ValueError):
        return record
    versions = [
        int(item.get("version") or 0)
        for item in unit.get("knowledge_outlines") or []
        if item.get("id") == record.get("knowledge_outline_id")
    ]
    if not versions:
        return record
    latest = max(versions)
    record["outline_latest_version"] = latest
    current = int(record.get("knowledge_outline_version") or 0)
    record["outline_has_newer_version"] = latest > current
    return record


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _clean_docx_filename(value: str) -> str:
    name = re.sub(r"[\x00-\x1f\x7f]+", "", Path(value).name).strip().rstrip(". ")
    name = re.sub(r'[<>:"/\\|?*]+', "-", name)
    if not name:
        name = "course-design.docx"
    if not name.lower().endswith(".docx"):
        name += ".docx"
    stem = Path(name).stem[:150].rstrip(". ") or "course-design"
    return f"{stem}.docx"


async def _resolve_template(record: dict, payload: CourseDesignExportRequest) -> tuple[Path | None, str | None, str | None, str]:
    settings = get_settings()
    material_id = (
        payload.template_material_id
        if "template_material_id" in payload.model_fields_set
        else record.get("template_material_id")
    )
    document_id = (
        payload.template_document_id
        if "template_document_id" in payload.model_fields_set
        else record.get("template_document_id")
    )
    template_name = "内置标准教案模板"
    if material_id:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, record["archive_id"])
        material = next((item for item in archive.get("materials", []) if item.get("id") == material_id), None)
        if not material:
            raise ValueError("所选模板不属于当前课程资料库")
        if str(material.get("extension", "")).lower() != ".docx" or not material.get("document_id"):
            raise ValueError("所选资料必须是已导入原件的 DOCX 教案模板")
        document_id = material["document_id"]
        template_name = material.get("name") or "资料库教案模板"
    elif document_id:
        template_name = "已上传自定义 DOCX 模板"
    if not document_id:
        return None, None, None, template_name
    template_path = await run_in_threadpool(original_path, settings.document_store_path, document_id)
    if template_path.suffix.lower() != ".docx":
        raise ValueError("教案模板必须为 DOCX 文件")
    return template_path, document_id, material_id, template_name


def _standard_template_inspection() -> dict:
    fields = [
        "course_name", "topic", "chapter", "session_label", "class_name", "location", "hours",
        "objectives", "knowledge_points", "key_points", "difficult_points", "methods", "tools",
        "ideological_elements", "teaching_process", "assessment", "postscript",
    ]
    return {
        "template_mode": "standard-template",
        "compatible": True,
        "matched_fields": fields,
        "unmatched_fields": [],
        "replacement_count": len(fields),
        "paragraph_count": 0,
        "table_count": 0,
        "header_count": 0,
        "footer_count": 0,
        "message": "使用平台内置可编辑教案模板，全部课程设计字段均可导出",
    }


def _resolve_knowledge_outline(payload: CourseDesignCreate, unit: dict | None, archive: dict | None = None) -> dict | None:
    if not payload.knowledge_outline_id:
        return None
    if unit is None:
        raise ValueError("未提供知识大纲所属的资料单元")
    if unit.get("archive_id") != payload.archive_id:
        raise ValueError("资料单元与课程资料库不匹配")
    candidates = [
        item for item in unit.get("knowledge_outlines", [])
        if item.get("id") == payload.knowledge_outline_id
    ]
    if payload.knowledge_outline_version is not None:
        candidates = [
            item for item in candidates
            if item.get("version") == payload.knowledge_outline_version
        ]
    if not candidates:
        requested = (
            f" v{payload.knowledge_outline_version}"
            if payload.knowledge_outline_version is not None
            else ""
        )
        raise FileNotFoundError(f"未找到指定的知识大纲{requested}")
    selected = max(candidates, key=lambda item: int(item.get("version", 0)))
    resolved = CourseDesignKnowledgeOutline.model_validate(selected).model_dump()
    if not resolved.get("session") and archive:
        schedule_ids = {
            str(item_id).rsplit(":", 1)[-1]
            for item_id in resolved.get("selected_session_ids", [])
        }
        schedule_items = [
            item for item in archive.get("schedule", [])
            if item.get("id") in schedule_ids
        ]
        resolved["session"] = "；".join(
            str(item.get("content") or item.get("label") or "").strip()
            for item in schedule_items
            if str(item.get("content") or item.get("label") or "").strip()
        )[:300]
    return resolved


@router.get("", response_model=CourseDesignList)
async def designs() -> CourseDesignList:
    records = await run_in_threadpool(list_designs, get_settings().course_design_store_path)
    return CourseDesignList(items=[CourseDesignSummary.model_validate(summary(item)) for item in records])


@router.post("", response_model=CourseDesignRecord, status_code=status.HTTP_201_CREATED)
async def create(payload: CourseDesignCreate) -> CourseDesignRecord:
    try:
        settings = get_settings()
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, payload.archive_id)
        unit = None
        if payload.material_unit_id:
            unit = await run_in_threadpool(
                load_material_unit,
                settings.material_unit_store_path,
                payload.material_unit_id,
            )
        outline = _resolve_knowledge_outline(payload, unit, archive)
        record = await run_in_threadpool(create_design, archive, payload, outline, unit)
        await run_in_threadpool(save_design, settings.course_design_store_path, record)
        return CourseDesignRecord.model_validate(public_record(record))
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except CrossArchiveReferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{design_id}", response_model=CourseDesignRecord)
async def design(design_id: str) -> CourseDesignRecord:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        record = await _attach_outline_status(record)
        return CourseDesignRecord.model_validate(public_record(record))
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc


@router.post("/{design_id}/rebind", response_model=CourseDesignRecord)
async def rebind_outline(design_id: str) -> CourseDesignRecord:
    """把课程设计重新绑定到资料单元大纲的最新版本（显式升级，不悄悄漂移）。

    升级后旧版本若不再被任何课程设计引用，delete_outline_version 的 409 锁自动解除。
    """
    try:
        settings = get_settings()
        record = await run_in_threadpool(load_design, settings.course_design_store_path, design_id)
        if not record.get("material_unit_id") or not record.get("knowledge_outline_id"):
            raise HTTPException(status_code=422, detail="本课程设计未绑定资料单元知识大纲，无法升级")
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, record["archive_id"])
        unit = await run_in_threadpool(
            load_material_unit, settings.material_unit_store_path, record["material_unit_id"]
        )
        # 重新绑定用最新版本：传 version=None 让 _resolve_knowledge_outline 取 max(version)
        payload = record_as_payload(record)
        payload.knowledge_outline_version = None
        outline = _resolve_knowledge_outline(payload, unit, archive)
        if outline is None or int(outline["version"]) <= int(record.get("knowledge_outline_version") or 0):
            raise HTTPException(status_code=409, detail="知识大纲已是当前最新版本，无需升级")
        updated = await run_in_threadpool(rebind_design, record, outline, archive)
        updated = await _attach_outline_status(updated)
        await run_in_threadpool(save_design, settings.course_design_store_path, updated)
        return CourseDesignRecord.model_validate(public_record(updated))
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def record_as_payload(record: dict) -> "CourseDesignCreate":
    return CourseDesignCreate(
        archive_id=record["archive_id"],
        chapter=record.get("chapter"),
        schedule_id=record.get("schedule_id"),
        material_ids=record.get("material_ids") or [],
        primary_material_id=record.get("primary_material_id"),
        material_unit_id=record.get("material_unit_id"),
        knowledge_outline_id=record.get("knowledge_outline_id"),
        knowledge_outline_version=record.get("knowledge_outline_version"),
    )


@router.put("/{design_id}", response_model=CourseDesignRecord)
async def update(design_id: str, payload: CourseDesignUpdate) -> CourseDesignRecord:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        if payload.base_version != record.get("version", 1):
            raise HTTPException(status_code=409, detail="课程设计已被更新，请刷新后再保存")
        # 「教师已审核」是一个有内容的承诺：没有教学目标/知识点/教学过程就退回 draft 才能
        # 说得通。过去这个开关不做任何校验，点一下数字就变，等于没有意义。
        if payload.status == "reviewed":
            blockers = review_blockers(payload.content)
            if blockers:
                raise HTTPException(
                    status_code=422,
                    detail="教案还缺少以下内容，补齐后才能标记为已审核：" + "、".join(blockers),
                )
        updated = await run_in_threadpool(
            update_design,
            record,
            payload.content,
            payload.status,
            payload.template_document_id,
            payload.template_material_id,
        )
        await run_in_threadpool(save_design, get_settings().course_design_store_path, updated)
        return CourseDesignRecord.model_validate(public_record(updated))
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc


@router.get("/{design_id}/versions", response_model=CourseDesignVersionList)
async def versions(design_id: str) -> CourseDesignVersionList:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        return CourseDesignVersionList(items=record.get("_versions", []))
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc


@router.post("/{design_id}/sync-run/{run_id}", response_model=CourseDesignRecord)
async def bind_run(design_id: str, run_id: str, request: Request) -> CourseDesignRecord:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        run = await request.app.state.workflow_service.get_run(run_id)
        if run.status != "completed":
            raise HTTPException(status_code=409, detail="多智能体会话尚未完成，不能同步空白或中间结果")
        draft = await request.app.state.workflow_service.repository.get_teacher_draft(run_id)
        updated = await run_in_threadpool(sync_run, record, run.model_dump(mode="json"), draft.content if draft else None)
        await run_in_threadpool(save_design, get_settings().course_design_store_path, updated)
        return CourseDesignRecord.model_validate(public_record(updated))
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class _AssemblyContext:
    """内容编排需要的全部上下文。

    用对象而不是元组：课堂来源需要额外的 classroom 载荷，元组再加字段会让每个
    调用点都得记住位置。
    """

    __slots__ = ("run_id", "run", "draft", "classroom", "warning")

    def __init__(self, run_id=None, run=None, draft=None, classroom=None, warning=None):
        self.run_id = run_id
        self.run = run
        self.draft = draft
        self.classroom = classroom
        self.warning = warning


async def _classroom_payload(request: Request, run_id: str) -> tuple[dict | None, str | None]:
    """读取一次课堂演练产物；读不到不是错误，只是少两类来源。"""
    repository = getattr(request.app.state, "classroom_repository", None)
    if repository is None:
        return None, "未连接到课堂演练数据库，逐页讲稿与督导评价暂不可用"
    try:
        lessons = await repository.list_lesson_versions(run_id)
        rounds = await repository.list_simulation_rounds(run_id)
    except Exception:
        return None, "课堂演练数据读取失败，逐页讲稿与督导评价暂不可用"
    if not lessons and not rounds:
        return None, None
    published = [item for item in lessons if item.status in ("ready", "final")]
    report = None
    for round_item in reversed(rounds):
        try:
            found = await repository.get_supervisor_report(round_item.id)
        except Exception:
            found = None
        if found is not None:
            report = found.model_dump(mode="json")
            break
    # 返回 {run_id: info} 映射，与 build_results 的 classroom 参数保持同一形状；
    # 单一载荷会被 _classroom_sources 当成"每个 key 是一个 run"而空转。
    return {
        run_id: {
            "run_id": run_id,
            "title": "",
            "lessons": [item.model_dump(mode="json") for item in (published or lessons)],
            "report": report,
        }
    }, None


async def _assembly_context(record: dict, run_id: str | None, request: Request) -> _AssemblyContext:
    # 语义区分（前端据此表达「仅使用进度表、大纲和知识范围」）：
    #   run_id == ""  → 教师显式不使用任何会话，直接返回空上下文，不回退 design.run_id；
    #   run_id is None → 未指定，回退到课程设计已绑定的 run_id；
    #   其他            → 使用显式指定的会话。
    if run_id == "":
        return _AssemblyContext()
    selected_run_id = run_id or record.get("run_id")
    if not selected_run_id:
        return _AssemblyContext()
    run = await request.app.state.workflow_service.get_run(selected_run_id)

    # 课堂演练的产出（逐页讲稿/督导评价）在 run 还是 paused 的时候就已经存在了，
    # 而教师想把它插进教案的时机往往正是那一刻。旧的 "必须 completed" 门把这一段
    # 直接挡在门外。改为：不完全依赖 run 状态的课堂产物始终可读；
    # 依赖 run.teaching_data 的来源（教师消息/思政）仍要求 completed。
    classroom, warning = await _classroom_payload(request, selected_run_id)
    if run.status != "completed":
        if classroom is not None:
            return _AssemblyContext(run_id=selected_run_id, classroom=classroom, warning=warning)
        if run_id is None:
            return _AssemblyContext()
        raise HTTPException(status_code=409, detail="所选会话尚未完成，暂时没有可插入成果")

    run_data = run.model_dump(mode="json")
    validate_run_context(record, run_data)
    draft = await request.app.state.workflow_service.repository.get_teacher_draft(selected_run_id)
    if classroom is not None:
        classroom["title"] = run_data.get("objective") or ""
    return _AssemblyContext(
        run_id=selected_run_id, run=run_data,
        draft=draft.content if draft else None,
        classroom=classroom, warning=warning,
    )


async def _restore_assembly_snapshot(record: dict) -> dict:
    settings = get_settings()
    archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, record["archive_id"])
    unit = None
    if record.get("material_unit_id"):
        try:
            unit = await run_in_threadpool(load_material_unit, settings.material_unit_store_path, record["material_unit_id"])
        except FileNotFoundError:
            unit = None
    return await run_in_threadpool(restore_source_snapshot, record, archive, unit)


@router.get("/{design_id}/assembly-sources", response_model=CourseDesignAssemblySourceList)
async def get_assembly_sources(
    design_id: str,
    request: Request,
    run_id: str | None = Query(
        default=None,
        description="省略=回退课程设计已绑定会话；空串=显式不使用任何会话；其他=指定会话",
    ),
) -> CourseDesignAssemblySourceList:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        record = await _restore_assembly_snapshot(record)
        ctx = await _assembly_context(record, run_id, request)
        items = await run_in_threadpool(
            assembly_sources, record, ctx.run, ctx.draft, ctx.classroom
        )
        return CourseDesignAssemblySourceList(
            design_id=design_id, run_id=ctx.run_id, items=items, warning=ctx.warning,
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{design_id}/assembly/apply", response_model=CourseDesignRecord)
async def assemble_design(
    design_id: str,
    payload: CourseDesignAssemblyApply,
    request: Request,
    run_id: str | None = Query(
        default=None,
        description="省略=回退课程设计已绑定会话；空串=显式不使用任何会话；其他=指定会话",
    ),
) -> CourseDesignRecord:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        record = await _restore_assembly_snapshot(record)
        if payload.base_version != record.get("version", 1):
            raise HTTPException(status_code=409, detail="课程设计已被更新，请刷新后重新插入")
        ctx = await _assembly_context(record, run_id, request)
        available = await run_in_threadpool(
            assembly_sources, record, ctx.run, ctx.draft, ctx.classroom
        )
        updated = await run_in_threadpool(apply_assembly, record, payload, available)
        # 只要插入了来自该会话的内容就建立绑定；课堂来源同样属于这个会话。
        if ctx.run_id and any(
            item.startswith((
                "teacher-message:", "teacher-draft:", "ideological:",
                "lesson:", "supervisor:",
            ))
            for item in payload.source_ids
        ):
            updated["run_id"] = ctx.run_id
        await run_in_threadpool(save_design, get_settings().course_design_store_path, updated)
        return CourseDesignRecord.model_validate(public_record(updated))
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{design_id}/references/{reference_id}", response_model=CourseReferenceDetail)
async def source(design_id: str, reference_id: str) -> CourseReferenceDetail:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        archive = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, record["archive_id"])
        detail = await run_in_threadpool(reference_detail, record, archive, reference_id)
        return CourseReferenceDetail.model_validate(detail)
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{design_id}/template-inspection", response_model=CourseDesignTemplateInspection)
async def inspect_template(design_id: str, payload: CourseDesignExportRequest) -> CourseDesignTemplateInspection:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        content = CourseDesignRecord.model_validate(public_record(record)).content
        template_path, _, _, _ = await _resolve_template(record, payload)
        report = (
            await run_in_threadpool(inspect_docx_template, template_path, content)
            if template_path else _standard_template_inspection()
        )
        report = {**report, "pending_fields": _pending_content_fields(content)}
        return CourseDesignTemplateInspection.model_validate(report)
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{design_id}/exports", response_model=CourseDesignExportList)
async def exports(design_id: str) -> CourseDesignExportList:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        items = [CourseDesignExportRecord.model_validate(item) for item in reversed(record.get("exports", []))]
        return CourseDesignExportList(items=items)
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc


@router.post("/{design_id}/export.docx")
async def export_docx(design_id: str, payload: CourseDesignExportRequest) -> Response:
    try:
        settings = get_settings()
        record = await run_in_threadpool(load_design, settings.course_design_store_path, design_id)
        template_path, template_document_id, template_material_id, template_name = await _resolve_template(record, payload)
        content, mode = await run_in_threadpool(build_docx, record, template_path, payload.preserve_source_format)
        report = (
            await run_in_threadpool(
                inspect_docx_template,
                template_path,
                CourseDesignRecord.model_validate(public_record(record)).content,
            )
            if template_path and mode == "source-template" else _standard_template_inspection()
        )
        filename = _clean_docx_filename(payload.filename or f"{record['title']}-可编辑教案.docx")
        export_id = str(uuid4())
        document_id = str(uuid4())
        await run_in_threadpool(persist_original, settings.document_store_path, document_id, filename, content)
        created_at = utc_now()
        export_record = {
            "id": export_id,
            "design_id": record["id"],
            "design_version": record.get("version", 1),
            "filename": filename,
            "document_id": document_id,
            "template_mode": mode,
            "template_document_id": template_document_id if mode == "source-template" else None,
            "template_material_id": template_material_id if mode == "source-template" else None,
            "template_name": template_name if mode == "source-template" else "内置标准教案模板",
            "matched_fields": report["matched_fields"],
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
            "preview_url": f"/api/documents/{document_id}/preview",
            "download_url": f"/api/documents/{document_id}/original",
            "created_at": created_at,
        }
        all_exports = [*record.get("exports", []), export_record]
        expired_exports = all_exports[:-30]
        record["exports"] = all_exports[-30:]
        record["updated_at"] = created_at
        # 导出成功 = 教师认可这一版，自动落到「教师已审核」。
        # 这给了 status 一个真实含义：它表示"当前内容已经过教师确认并交付过"，
        # 而不是一个需要教师额外去点、点了也不影响任何行为的开关。
        record["status"] = "reviewed"
        try:
            await run_in_threadpool(save_design, settings.course_design_store_path, record)
        except Exception:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
            raise
        for expired in expired_exports:
            if expired.get("document_id"):
                await run_in_threadpool(delete_document, settings.document_store_path, expired["document_id"])
        fallback = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "course-design.docx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}",
                "X-Template-Mode": mode,
                "X-Export-ID": export_id,
                "X-Document-ID": document_id,
                "X-Matched-Fields": str(len(report["matched_fields"])),
            },
        )
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{design_id}/exports/{export_id}", status_code=204)
async def remove_export(design_id: str, export_id: str) -> Response:
    try:
        settings = get_settings()
        record = await run_in_threadpool(load_design, settings.course_design_store_path, design_id)
        export_record = next((item for item in record.get("exports", []) if item.get("id") == export_id), None)
        if not export_record:
            raise FileNotFoundError("未找到指定的导出成果")
        record["exports"] = [item for item in record.get("exports", []) if item.get("id") != export_id]
        record["updated_at"] = utc_now()
        await run_in_threadpool(save_design, settings.course_design_store_path, record)
        if export_record.get("document_id"):
            await run_in_threadpool(delete_document, settings.document_store_path, export_record["document_id"])
        return Response(status_code=204)
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc


@router.delete("/{design_id}", status_code=204)
async def remove(design_id: str) -> Response:
    try:
        settings = get_settings()
        record = await run_in_threadpool(load_design, settings.course_design_store_path, design_id)
        await run_in_threadpool(delete_design, settings.course_design_store_path, design_id)
        for item in record.get("exports", []):
            if item.get("document_id"):
                await run_in_threadpool(delete_document, settings.document_store_path, item["document_id"])
        return Response(status_code=204)
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc
