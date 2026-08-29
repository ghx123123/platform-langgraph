import hashlib
import re
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
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
    public_record, reference_detail, restore_source_snapshot, summary, sync_run, update_design,
    utc_now, validate_run_context,
)
from backend.course_designs.storage import delete_design, list_designs, load_design, save_design
from backend.documents.storage import delete_document, original_path, persist_original
from backend.material_units.storage import load_material_unit


router = APIRouter(prefix="/api/course-designs", tags=["course-designs"])


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
        record = await run_in_threadpool(create_design, archive, payload, outline)
        await run_in_threadpool(save_design, settings.course_design_store_path, record)
        return CourseDesignRecord.model_validate(public_record(record))
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{design_id}", response_model=CourseDesignRecord)
async def design(design_id: str) -> CourseDesignRecord:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        return CourseDesignRecord.model_validate(public_record(record))
    except (FileNotFoundError, ValueError) as exc:
        raise _not_found(exc) from exc


@router.put("/{design_id}", response_model=CourseDesignRecord)
async def update(design_id: str, payload: CourseDesignUpdate) -> CourseDesignRecord:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        if payload.base_version != record.get("version", 1):
            raise HTTPException(status_code=409, detail="课程设计已被更新，请刷新后再保存")
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


async def _assembly_context(record: dict, run_id: str | None, request: Request) -> tuple[str | None, dict | None, str | None]:
    selected_run_id = run_id or record.get("run_id")
    if not selected_run_id:
        return None, None, None
    run = await request.app.state.workflow_service.get_run(selected_run_id)
    if run.status != "completed":
        if run_id is None:
            return None, None, None
        raise HTTPException(status_code=409, detail="所选会话尚未完成，暂时没有可插入成果")
    run_data = run.model_dump(mode="json")
    validate_run_context(record, run_data)
    draft = await request.app.state.workflow_service.repository.get_teacher_draft(selected_run_id)
    return selected_run_id, run_data, draft.content if draft else None


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
    design_id: str, request: Request, run_id: str | None = None,
) -> CourseDesignAssemblySourceList:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        record = await _restore_assembly_snapshot(record)
        selected_run_id, run_data, teacher_draft = await _assembly_context(record, run_id, request)
        items = await run_in_threadpool(assembly_sources, record, run_data, teacher_draft)
        return CourseDesignAssemblySourceList(design_id=design_id, run_id=selected_run_id, items=items)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise _not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{design_id}/assembly/apply", response_model=CourseDesignRecord)
async def assemble_design(
    design_id: str, payload: CourseDesignAssemblyApply, request: Request,
    run_id: str | None = None,
) -> CourseDesignRecord:
    try:
        record = await run_in_threadpool(load_design, get_settings().course_design_store_path, design_id)
        record = await _restore_assembly_snapshot(record)
        if payload.base_version != record.get("version", 1):
            raise HTTPException(status_code=409, detail="课程设计已被更新，请刷新后重新插入")
        selected_run_id, run_data, teacher_draft = await _assembly_context(record, run_id, request)
        available = await run_in_threadpool(assembly_sources, record, run_data, teacher_draft)
        updated = await run_in_threadpool(apply_assembly, record, payload, available)
        if selected_run_id and any(
            item.startswith(("teacher-message:", "teacher-draft:", "ideological:"))
            for item in payload.source_ids
        ):
            updated["run_id"] = selected_run_id
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
        template_path, _, _, _ = await _resolve_template(record, payload)
        report = (
            await run_in_threadpool(
                inspect_docx_template,
                template_path,
                CourseDesignRecord.model_validate(public_record(record)).content,
            )
            if template_path else _standard_template_inspection()
        )
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
