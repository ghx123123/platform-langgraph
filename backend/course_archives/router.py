import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import TypeAdapter, ValidationError

from backend.core.config import get_settings
from backend.course_archives.models import (
    ArchiveManifestItem,
    ArchiveDeletionImpact,
    ArchiveDeletionResult,
    CourseArchiveDetail,
    CourseArchiveList,
    CourseArchiveSummary,
    ExtractArchiveRequest,
    PreparationPack,
    PrepareArchiveRequest,
)
from backend.course_archives.deletion import deletion_impact, public_deletion_impact
from backend.course_archives.service import (
    analyze_course_archive,
    archive_summary,
    extract_course_archive_materials,
    prepare_archive_pack,
    public_archive,
)
from backend.course_archives.storage import delete_archive, list_archives, load_archive, save_archive
from backend.material_units.storage import delete_material_units_for_archive
from backend.course_designs.storage import delete_designs_for_archive, list_designs
from backend.data_hub.storage import (
    delete_compositions_for_archive,
    delete_layouts_for_archive,
    list_compositions,
    list_layouts,
)
from backend.documents.storage import delete_document


router = APIRouter(prefix="/api/course-archives", tags=["course-archives"])
manifest_adapter = TypeAdapter(list[ArchiveManifestItem])
MAX_MANIFEST_ITEMS = 6000
MAX_UPLOAD_FILES = 6000
MAX_UPLOAD_TOTAL_BYTES = 360 * 1024 * 1024


@router.get("", response_model=CourseArchiveList)
async def archives() -> CourseArchiveList:
    records = await run_in_threadpool(list_archives, get_settings().course_archive_store_path)
    return CourseArchiveList(items=[CourseArchiveSummary.model_validate(archive_summary(item)) for item in records])


@router.get("/{archive_id}", response_model=CourseArchiveDetail)
async def archive(archive_id: str) -> CourseArchiveDetail:
    try:
        record = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, archive_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到学期资料库") from exc
    return CourseArchiveDetail.model_validate(public_archive(record))


@router.post("/analyze", response_model=CourseArchiveDetail, status_code=201)
async def analyze(
    manifest: str = Form(...),
    archive_name: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
) -> CourseArchiveDetail:
    try:
        manifest_items = manifest_adapter.validate_json(manifest)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="文件夹清单格式无效") from exc
    if not manifest_items:
        raise HTTPException(status_code=422, detail="文件夹中没有可分析的教学资料")
    if len(manifest_items) > MAX_MANIFEST_ITEMS:
        raise HTTPException(status_code=422, detail=f"单次最多分析 {MAX_MANIFEST_ITEMS} 个文件")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=422, detail=f"单次最多深度解析 {MAX_UPLOAD_FILES} 份优先材料")
    uploads: list[tuple[str, bytes]] = []
    total = 0
    for upload in files:
        data = await upload.read()
        total += len(data)
        if total > MAX_UPLOAD_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="深度解析材料总大小不能超过 360 MB")
        uploads.append((upload.filename or "material.txt", data))
    record = await run_in_threadpool(
        analyze_course_archive,
        archive_name,
        manifest_items,
        uploads,
        get_settings().document_store_path,
        None,
        None,
        False,
    )
    await run_in_threadpool(save_archive, get_settings().course_archive_store_path, record)
    return CourseArchiveDetail.model_validate(public_archive(record))


@router.post("/{archive_id}/extract", response_model=CourseArchiveDetail)
async def extract_materials(archive_id: str, payload: ExtractArchiveRequest) -> CourseArchiveDetail:
    settings = get_settings()
    try:
        record = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        record = await run_in_threadpool(
            extract_course_archive_materials,
            record,
            payload.material_ids,
            settings.document_store_path,
        )
        await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
        return CourseArchiveDetail.model_validate(public_archive(record))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到课程资料库或原始文件") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{archive_id}/prepare", response_model=PreparationPack)
async def prepare(archive_id: str, payload: PrepareArchiveRequest) -> PreparationPack:
    try:
        record = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, archive_id)
        pack = await run_in_threadpool(prepare_archive_pack, record, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到学期资料库") from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PreparationPack.model_validate(pack)


async def _deletion_context(archive_id: str, request: Request) -> tuple[dict, dict]:
    settings = get_settings()
    try:
        archive_record = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到学期资料库") from exc
    designs, compositions, layouts = await run_in_threadpool(
        lambda: (
            list_designs(settings.course_design_store_path),
            list_compositions(settings.data_hub_store_path),
            list_layouts(settings.data_hub_store_path),
        )
    )
    runs = [item.model_dump(mode="json") for item in await request.app.state.workflow_service.repository.list_runs(limit=10000)]
    impact = await run_in_threadpool(deletion_impact, archive_record, designs, runs, compositions, layouts)
    return archive_record, impact


@router.get("/{archive_id}/deletion-impact", response_model=ArchiveDeletionImpact)
async def inspect_deletion(archive_id: str, request: Request) -> ArchiveDeletionImpact:
    _, impact = await _deletion_context(archive_id, request)
    return ArchiveDeletionImpact.model_validate(public_deletion_impact(impact))


@router.delete("/{archive_id}", response_model=ArchiveDeletionResult)
async def remove(archive_id: str, request: Request) -> ArchiveDeletionResult:
    settings = get_settings()
    _, impact = await _deletion_context(archive_id, request)

    # Stop active linked workflows before removing their persistent records.
    for run in impact["_runs"]:
        try:
            await request.app.state.workflow_service.delete_run(run["id"])
        except FileNotFoundError:
            continue

    await run_in_threadpool(delete_designs_for_archive, settings.course_design_store_path, archive_id)
    await run_in_threadpool(delete_compositions_for_archive, settings.data_hub_store_path, archive_id)
    await run_in_threadpool(delete_layouts_for_archive, settings.data_hub_store_path, archive_id)
    await run_in_threadpool(delete_material_units_for_archive, settings.material_unit_store_path, archive_id)
    for document_id in impact["_document_ids"]:
        await run_in_threadpool(delete_document, settings.document_store_path, document_id)
    await run_in_threadpool(delete_archive, settings.course_archive_store_path, archive_id)

    return ArchiveDeletionResult.model_validate({**public_deletion_impact(impact), "deleted": True})
