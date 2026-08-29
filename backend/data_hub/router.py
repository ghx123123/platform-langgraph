import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response

from backend.core.config import get_settings
from backend.course_archives.service import append_course_archive_files, public_archive, remove_course_archive_materials
from backend.course_archives.storage import list_archives, load_archive, save_archive
from backend.course_archives.models import CourseArchiveDetail
from backend.course_designs.storage import list_designs
from backend.data_hub.models import (
    AcademicTermRename, AcademicTermRenameResult, ArchiveMetadataUpdate, CompositionCreate, CompositionList, CompositionRecord,
    BrowserSourceRegisterRequest, ExternalOpenResult, MaterialReloadResult,
    CompositionSummary, CompositionUpdate, DataHubBlock, DataHubBlocksMove, DataHubBlockUpdate, DataHubCatalog,
    DataHubBlocksDelete, DataHubLayout, DataHubUploadResult, FolderCreate, FolderUpdate, ImportFolderOrganizeRequest,
    ImportFolderOrganizeResult, LibraryRootCreate, LibraryRootUpdate, LocalSourceScanRequest, LocalSourceScanResult,
    LocalFolderSyncRequest, LocalMaterialTransferRequest, LocalSourceDiffResult, LocalSourceReconcileRequest,
    LocalSourceReconcileResult, LocalSyncResult, SourceFolderResult, SourceUploadResult,
)
from backend.data_hub.service import (
    apply_layouts, block_detail, build_catalog, composition_docx, composition_html, composition_markdown,
    composition_summary, create_composition, filter_catalog, import_composition,
    create_data_folder, delete_data_folder, delete_data_folder_recursive, ensure_data_folder_path, folder_subtree_ids,
    apply_platform_to_local, local_source_diff, organize_imported_archive, record_local_deletions,
    remove_blocks_from_layout, resolve_local_folder_path, scan_local_source,
    sync_folder_to_local, sync_uploads_to_local, transfer_local_materials, update_block_layout,
    create_library_root, organize_source_archive, register_source_manifest, rename_academic_term, rename_library_root,
    update_composition, update_data_folder, utc_now,
)
from backend.data_hub.storage import (
    delete_composition, list_compositions, list_layouts, load_composition, load_layout,
    save_composition, save_layout,
)
from backend.documents.storage import delete_document
from backend.documents.storage import original_path
from backend.course_archives.models import ArchiveManifestItem
from backend.course_archives.service import store_course_archive_originals
from backend.data_hub.external import open_with_system


router = APIRouter(prefix="/api/data-hub", tags=["data-hub"])
MAX_HUB_UPLOAD_FILES = 1000
MAX_HUB_UPLOAD_BYTES = 360 * 1024 * 1024


async def _source_records(request: Request) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    settings = get_settings()
    archives = await run_in_threadpool(list_archives, settings.course_archive_store_path)
    designs = await run_in_threadpool(list_designs, settings.course_design_store_path)
    runs = await request.app.state.workflow_service.repository.list_runs(limit=200)
    compositions = await run_in_threadpool(list_compositions, settings.data_hub_store_path)
    layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
    return archives, designs, [item.model_dump(mode="json") for item in runs], compositions, layouts


@router.get("/catalog", response_model=DataHubCatalog)
async def catalog(
    request: Request,
    q: str = Query(default="", max_length=120),
    term: str = Query(default="", max_length=80),
    course: str = Query(default="", max_length=160),
    kind: str = Query(default="", max_length=40),
    summary_only: bool = Query(default=False),
    unit_id: str = Query(default="", max_length=120),
) -> DataHubCatalog:
    archives, designs, runs, compositions, layouts = await _source_records(request)
    if summary_only:
        layouts = []
    if unit_id:
        archive_id = unit_id.split(":", 1)[0]
        archives = [item for item in archives if item.get("id") == archive_id]
        designs = [item for item in designs if item.get("archive_id") == archive_id]
        compositions = [item for item in compositions if item.get("archive_id") == archive_id or item.get("unit_id") == unit_id]
        layouts = [item for item in layouts if item.get("unit_id") == unit_id]
    result = await run_in_threadpool(
        build_catalog, archives, designs, runs, compositions, not summary_only, unit_id or None,
    )
    arranged = await run_in_threadpool(apply_layouts, result, layouts)
    filtered = filter_catalog(arranged, q, term, course, kind)
    if unit_id:
        filtered["units"] = [item for item in filtered["units"] if item.get("id") == unit_id]
        filtered["folders"] = [item for item in filtered.get("folders", []) if item.get("unit_id") == unit_id]
        filtered["blocks"] = [item for item in filtered["blocks"] if item.get("unit_id") == unit_id]
    return DataHubCatalog.model_validate(filtered)


@router.get("/blocks/{block_id:path}", response_model=DataHubBlock)
async def content_block(block_id: str, request: Request) -> DataHubBlock:
    archives, designs, runs, compositions, layouts = await _source_records(request)
    catalog_data = await run_in_threadpool(build_catalog, archives, designs, runs, compositions)
    catalog_data = await run_in_threadpool(apply_layouts, catalog_data, layouts)
    try:
        return DataHubBlock.model_validate(await run_in_threadpool(block_detail, block_id, catalog_data, archives))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/library-roots", response_model=CourseArchiveDetail, status_code=status.HTTP_201_CREATED)
async def create_root(payload: LibraryRootCreate) -> CourseArchiveDetail:
    settings = get_settings()
    archives = await run_in_threadpool(list_archives, settings.course_archive_store_path)
    try:
        record = await run_in_threadpool(create_library_root, archives, payload.name, settings.document_store_path)
        await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CourseArchiveDetail.model_validate(public_archive(record))


@router.patch("/library-roots/{archive_id}", response_model=CourseArchiveDetail)
async def rename_root(archive_id: str, payload: LibraryRootUpdate) -> CourseArchiveDetail:
    settings = get_settings()
    archives = await run_in_threadpool(list_archives, settings.course_archive_store_path)
    try:
        record = await run_in_threadpool(rename_library_root, archives, archive_id, payload.name)
        await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CourseArchiveDetail.model_validate(public_archive(record))


@router.put("/archives/{archive_id}/metadata")
async def update_archive_metadata(archive_id: str, payload: ArchiveMetadataUpdate) -> dict:
    settings = get_settings()
    try:
        record = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到课程资料库") from exc
    record.update({
        "academic_term": payload.academic_term.strip(),
        "course_title": payload.course_title.strip(),
        "course_code": payload.course_code.strip(),
        "updated_at": utc_now(),
    })
    await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
    return public_archive(record)


@router.put("/academic-terms/rename", response_model=AcademicTermRenameResult)
async def rename_term(payload: AcademicTermRename) -> AcademicTermRenameResult:
    settings = get_settings()
    archives = await run_in_threadpool(list_archives, settings.course_archive_store_path)
    try:
        updated = await run_in_threadpool(rename_academic_term, archives, payload.current_name, payload.new_name)
        for record in updated:
            await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AcademicTermRenameResult(
        previous_name=payload.current_name.strip(),
        academic_term=payload.new_name.strip(),
        updated_courses=len(updated),
    )


@router.post("/local-sources/scan", response_model=LocalSourceScanResult)
async def scan_local(payload: LocalSourceScanRequest) -> LocalSourceScanResult:
    settings = get_settings()
    existing = None
    if payload.archive_id:
        try:
            existing = await run_in_threadpool(load_archive, settings.course_archive_store_path, payload.archive_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到需要更新的课程资料库") from exc
    metadata = {
        "archive_name": payload.archive_name,
        "academic_term": payload.academic_term.strip(),
        "course_title": payload.course_title.strip(),
        "course_code": payload.course_code.strip(),
    }
    try:
        record, source, changes, removed_document_ids = await run_in_threadpool(
            scan_local_source, payload.root_path, existing, metadata, settings.document_store_path,
            payload.source_id, payload.source_name,
        )
        await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
        for document_id in removed_document_ids:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
        archives = [record]
        catalog_data = await run_in_threadpool(build_catalog, archives, [], [], [])
        layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
        changed_layouts, _ = await run_in_threadpool(organize_source_archive, catalog_data, layouts, record["id"], source)
        for layout in changed_layouts:
            await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LocalSourceScanResult(
        archive_id=record["id"], archive_name=record["name"], local_root=record["local_root"],
        changes=changes, total_files=record["total_files"], total_directories=source.get("directory_count", 0), warnings=record.get("warnings", []),
        source_id=source["id"], source_name=source["name"], source_kind="local",
    )


@router.post("/sources/browser", response_model=SourceFolderResult, status_code=status.HTTP_201_CREATED)
async def register_browser_source(payload: BrowserSourceRegisterRequest) -> SourceFolderResult:
    settings = get_settings()
    existing = None
    if payload.archive_id:
        try:
            existing = await run_in_threadpool(load_archive, settings.course_archive_store_path, payload.archive_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="未找到目标课程资料库") from exc
    manifest = [ArchiveManifestItem(path=item.path, size=item.size, last_modified=item.last_modified) for item in payload.manifest]
    if not manifest and payload.selection_kind != "folder":
        raise HTTPException(status_code=422, detail="请选择至少一个文件")
    metadata = {
        "archive_name": payload.course_title or payload.source_name,
        "academic_term": payload.academic_term.strip(),
        "course_title": payload.course_title.strip() or (existing or {}).get("course_title") or payload.source_name,
        "course_code": payload.course_code.strip(),
    }
    try:
        record, source, changes, removed_document_ids = await run_in_threadpool(
            register_source_manifest, existing, payload.source_name, "upload", manifest,
            metadata, settings.document_store_path, payload.source_id, None, payload.selection_kind,
            payload.directories, payload.parent_folder_id,
        )
        changes.pop("_changed_paths", None)
        catalog_data = await run_in_threadpool(build_catalog, [record], [], [], [])
        layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
        changed_layouts, _ = await run_in_threadpool(
            organize_source_archive, catalog_data, layouts, record["id"], source,
        )
        await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
        for layout in changed_layouts:
            await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
        for document_id in removed_document_ids:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SourceFolderResult(archive_id=record["id"], source=source, changes=changes, total_files=record["total_files"])


@router.post("/archives/{archive_id}/sources/{source_id}/files", response_model=SourceUploadResult)
async def upload_source_files(archive_id: str, source_id: str, files: list[UploadFile] = File(...)) -> SourceUploadResult:
    if not files or len(files) > 120:
        raise HTTPException(status_code=422, detail="每批可上传 1 至 120 个文件")
    settings = get_settings()
    try:
        record = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到目标课程资料库") from exc
    source = next((item for item in record.get("source_folders", []) if item.get("id") == source_id), None)
    if not source or source.get("kind") != "upload":
        raise HTTPException(status_code=404, detail="未找到上传来源文件夹")
    uploads: list[tuple[str, bytes]] = []
    total_bytes = 0
    for upload in files:
        data = await upload.read()
        total_bytes += len(data)
        limit = 360 * 1024 * 1024 if len(files) == 1 else 80 * 1024 * 1024
        if total_bytes > limit:
            raise HTTPException(status_code=413, detail="多文件批次不能超过 80 MB，单个文件不能超过 360 MB")
        uploads.append((upload.filename or "未命名资料", data))
    try:
        record, uploaded, replaced = await run_in_threadpool(
            store_course_archive_originals, record, uploads, settings.document_store_path,
        )
        await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
        for document_id in replaced:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SourceUploadResult(archive_id=archive_id, source_id=source_id, uploaded=uploaded, total_files=record["total_files"])


@router.post("/archives/{archive_id}/sources/{source_id}/organize")
async def organize_source(archive_id: str, source_id: str, request: Request) -> dict:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到课程资料库") from exc
    source = next((item for item in archive.get("source_folders", []) if item.get("id") == source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="未找到来源文件夹")
    _, designs, runs, compositions, layouts = await _source_records(request)
    catalog_data = await run_in_threadpool(build_catalog, [archive], designs, runs, compositions)
    changed_layouts, summary = await run_in_threadpool(organize_source_archive, catalog_data, layouts, archive_id, source)
    for layout in changed_layouts:
        await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
    return summary


@router.post("/archives/{archive_id}/sources/{source_id}/refresh", response_model=LocalSourceScanResult)
async def refresh_source(archive_id: str, source_id: str) -> LocalSourceScanResult:
    settings = get_settings()
    try:
        existing = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到课程资料库") from exc
    source = next((item for item in existing.get("source_folders", []) if item.get("id") == source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="未找到来源文件夹")
    if source.get("kind") != "local" or not source.get("root_path"):
        raise HTTPException(status_code=409, detail="上传副本无法自动读取原路径，请重新选择同一文件夹进行更新")
    try:
        record, source, changes, removed_document_ids = await run_in_threadpool(
            scan_local_source, source["root_path"], existing, {}, settings.document_store_path,
            source_id, source["name"],
        )
        await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
        for document_id in removed_document_ids:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
        catalog_data = await run_in_threadpool(build_catalog, [record], [], [], [])
        layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
        changed_layouts, _ = await run_in_threadpool(organize_source_archive, catalog_data, layouts, archive_id, source)
        for layout in changed_layouts:
            await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LocalSourceScanResult(
        archive_id=record["id"], archive_name=record["name"], local_root=source["root_path"],
        changes=changes, total_files=record["total_files"], total_directories=source.get("directory_count", 0), warnings=record.get("warnings", []),
        source_id=source["id"], source_name=source["name"], source_kind="local",
    )


@router.get("/archives/{archive_id}/sources/{source_id}/diff", response_model=LocalSourceDiffResult)
async def inspect_source_diff(archive_id: str, source_id: str) -> LocalSourceDiffResult:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        source = next((item for item in archive.get("source_folders", []) if item.get("id") == source_id), None)
        if not source:
            raise KeyError("未找到来源文件夹")
        unit = next((item for item in await run_in_threadpool(list_layouts, settings.data_hub_store_path) if str(item.get("unit_id", "")).startswith(f"{archive_id}:") and any(folder.get("source_folder_id") == source_id for folder in item.get("folders", []))), None)
        if not unit:
            raise KeyError("未找到来源目录布局")
        result = await run_in_threadpool(local_source_diff, archive, unit, source_id, settings.document_store_path)
        return LocalSourceDiffResult.model_validate(result)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/archives/{archive_id}/sources/{source_id}/reconcile", response_model=LocalSourceReconcileResult)
async def reconcile_source(archive_id: str, source_id: str, payload: LocalSourceReconcileRequest) -> LocalSourceReconcileResult:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        source = next((item for item in archive.get("source_folders", []) if item.get("id") == source_id), None)
        if not source:
            raise KeyError("未找到来源文件夹")
        layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
        layout = next((item for item in layouts if str(item.get("unit_id", "")).startswith(f"{archive_id}:") and any(folder.get("source_folder_id") == source_id for folder in item.get("folders", []))), None)
        if not layout:
            raise KeyError("未找到来源目录布局")
        if payload.direction == "update_platform":
            before = await run_in_threadpool(local_source_diff, archive, layout, source_id, settings.document_store_path)
            archive["_local_sync_deletions"] = {
                key: value for key, value in archive.get("_local_sync_deletions", {}).items() if value.get("source_id") != source_id
            }
            record, refreshed_source, changes, removed_document_ids = await run_in_threadpool(
                scan_local_source, source["root_path"], archive, {}, settings.document_store_path, source_id, source["name"],
            )
            await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
            for document_id in removed_document_ids:
                await run_in_threadpool(delete_document, settings.document_store_path, document_id)
            catalog_data = await run_in_threadpool(build_catalog, [record], [], [], [])
            changed_layouts, _ = await run_in_threadpool(organize_source_archive, catalog_data, layouts, archive_id, refreshed_source)
            for changed_layout in changed_layouts:
                await run_in_threadpool(save_layout, settings.data_hub_store_path, changed_layout)
            applied = len(before["items"])
            skipped = 0
            message = f"已按本地目录更新平台：新增 {changes['added']}、修改 {changes['changed']}、移除 {changes['removed']}。"
        else:
            applied, skipped = await run_in_threadpool(apply_platform_to_local, archive, layout, source_id, settings.document_store_path)
            await run_in_threadpool(save_archive, settings.course_archive_store_path, archive)
            record, refreshed_source, _, removed_document_ids = await run_in_threadpool(
                scan_local_source, source["root_path"], archive, {}, settings.document_store_path, source_id, source["name"],
            )
            await run_in_threadpool(save_archive, settings.course_archive_store_path, record)
            for document_id in removed_document_ids:
                await run_in_threadpool(delete_document, settings.document_store_path, document_id)
            catalog_data = await run_in_threadpool(build_catalog, [record], [], [], [])
            changed_layouts, _ = await run_in_threadpool(organize_source_archive, catalog_data, layouts, archive_id, refreshed_source)
            for changed_layout in changed_layouts:
                await run_in_threadpool(save_layout, settings.data_hub_store_path, changed_layout)
            message = f"已按平台记录更新本地：处理 {applied} 项，跳过 {skipped} 项。"
        return LocalSourceReconcileResult(
            archive_id=archive_id, source_id=source_id, direction=payload.direction,
            applied=applied, skipped=skipped, message=message,
        )
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileExistsError, ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/archives/{archive_id}/sources/{source_id}/open", response_model=ExternalOpenResult)
async def open_source_folder(archive_id: str, source_id: str) -> ExternalOpenResult:
    try:
        archive = await run_in_threadpool(load_archive, get_settings().course_archive_store_path, archive_id)
        source = next(item for item in archive.get("source_folders", []) if item.get("id") == source_id)
        if source.get("kind") != "local" or not source.get("root_path"):
            raise ValueError("上传副本没有可打开的本机源文件夹")
        target = Path(source["root_path"])
        await run_in_threadpool(open_with_system, target)
        return ExternalOpenResult(target=str(target), message="已使用系统文件管理器打开来源文件夹")
    except (FileNotFoundError, StopIteration) as exc:
        raise HTTPException(status_code=404, detail="本机来源文件夹已不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _material_and_source(archive: dict, material_id: str) -> tuple[dict, dict | None]:
    material = next((item for item in archive.get("materials", []) if item.get("id") == material_id), None)
    if not material:
        raise KeyError("未找到原始文件")
    source = next((item for item in archive.get("source_folders", []) if item.get("id") == material.get("source_folder_id")), None)
    return material, source


def _safe_local_material_path(source: dict, material: dict) -> Path:
    root = Path(source["root_path"]).expanduser().resolve()
    target = (root / str(material.get("source_relative_path") or material["name"])).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("本机文件路径超出来源目录") from exc
    return target


@router.post("/archives/{archive_id}/materials/{material_id}/open", response_model=ExternalOpenResult)
async def open_material(archive_id: str, material_id: str) -> ExternalOpenResult:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        material, source = _material_and_source(archive, material_id)
        if source and source.get("kind") == "local" and source.get("root_path"):
            target = _safe_local_material_path(source, material)
        elif material.get("document_id"):
            target = await run_in_threadpool(original_path, settings.document_store_path, material["document_id"])
        else:
            raise FileNotFoundError("平台尚未保存该文件副本")
        await run_in_threadpool(open_with_system, target)
        return ExternalOpenResult(target=str(target), message="已使用系统默认程序打开文件")
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/archives/{archive_id}/materials/{material_id}/reload", response_model=MaterialReloadResult)
async def reload_material(archive_id: str, material_id: str) -> MaterialReloadResult:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        material, source = _material_and_source(archive, material_id)
        if not source or source.get("kind") != "local" or not source.get("root_path"):
            raise ValueError("上传副本无法读取原路径，请重新选择来源文件夹更新")
        target = _safe_local_material_path(source, material)
        if not target.is_file():
            raise FileNotFoundError("本机源文件已不存在")
        stat = target.stat()
        material["size"] = stat.st_size
        material["last_modified"] = int(stat.st_mtime * 1000)
        archive, updated, replaced = await run_in_threadpool(
            store_course_archive_originals, archive, [(material["path"], target.read_bytes())], settings.document_store_path,
        )
        await run_in_threadpool(save_archive, settings.course_archive_store_path, archive)
        for document_id in replaced:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
        return MaterialReloadResult(
            archive_id=archive_id, material_id=material_id, reloaded=updated > 0,
            updated_at=archive["updated_at"],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/archives/{archive_id}/sources/{source_id}", status_code=204)
async def delete_source_folder(archive_id: str, source_id: str) -> Response:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        source = next((item for item in archive.get("source_folders", []) if item.get("id") == source_id), None)
        if not source:
            raise KeyError("未找到来源文件夹")
        material_ids = {item["id"] for item in archive.get("materials", []) if item.get("source_folder_id") == source_id}
        document_ids: list[str] = []
        if material_ids:
            archive, document_ids = await run_in_threadpool(remove_course_archive_materials, archive, material_ids)
        archive["source_folders"] = [item for item in archive.get("source_folders", []) if item.get("id") != source_id]
        await run_in_threadpool(save_archive, settings.course_archive_store_path, archive)
        layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
        block_ids = {
            f"material:{archive_id}:{material_id}:{kind}"
            for material_id in material_ids for kind in ("original", "extracted")
        }
        for layout in layouts:
            if not str(layout.get("unit_id", "")).startswith(f"{archive_id}:"):
                continue
            updated = await run_in_threadpool(remove_blocks_from_layout, layout, block_ids)
            roots = [item for item in updated.get("folders", []) if item.get("source_folder_id") == source_id]
            for root in roots:
                updated, _ = await run_in_threadpool(delete_data_folder_recursive, updated, root["id"])
            await run_in_threadpool(save_layout, settings.data_hub_store_path, updated)
        for document_id in document_ids:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
        return Response(status_code=204)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _layout_with_folder(layouts: list[dict], folder_id: str) -> dict:
    layout = next((item for item in layouts if any(folder["id"] == folder_id for folder in item.get("folders", []))), None)
    if not layout:
        raise KeyError("未找到资料文件夹")
    return layout


def _material_id_from_block(block_id: str) -> tuple[str, str]:
    parts = block_id.split(":")
    if len(parts) != 4 or parts[0] != "material" or parts[3] != "original":
        raise ValueError("数据中台只允许删除原始文件")
    return parts[1], parts[2]


async def _delete_original_blocks(unit_id: str, block_ids: list[str]) -> int:
    identities = [_material_id_from_block(block_id) for block_id in block_ids]
    archive_ids = {archive_id for archive_id, _ in identities}
    if len(archive_ids) != 1 or not unit_id.startswith(f"{next(iter(archive_ids))}:"):
        raise ValueError("只能删除当前课程单元中的原始文件")
    archive_id = next(iter(archive_ids))
    material_ids = {material_id for _, material_id in identities}
    settings = get_settings()
    record = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
    record = await run_in_threadpool(record_local_deletions, record, material_ids)
    updated, document_ids = await run_in_threadpool(remove_course_archive_materials, record, material_ids)
    layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, unit_id)
    related_block_ids = {
        f"material:{archive_id}:{material_id}:{kind}"
        for material_id in material_ids
        for kind in ("original", "extracted")
    }
    layout = await run_in_threadpool(remove_blocks_from_layout, layout, related_block_ids)
    await run_in_threadpool(save_archive, settings.course_archive_store_path, updated)
    await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
    for document_id in document_ids:
        await run_in_threadpool(delete_document, settings.document_store_path, document_id)
    return len(material_ids)


@router.post("/uploads", response_model=DataHubUploadResult, status_code=status.HTTP_201_CREATED)
async def upload_to_directory(
    request: Request,
    unit_id: str = Form(...),
    folder_id: str = Form(default=""),
    destination_path: str = Form(default="[]"),
    files: list[UploadFile] = File(...),
) -> DataHubUploadResult:
    if not files or len(files) > MAX_HUB_UPLOAD_FILES:
        raise HTTPException(status_code=422, detail=f"单次可上传 1 至 {MAX_HUB_UPLOAD_FILES} 个文件")
    try:
        path_parts = json.loads(destination_path)
        if not isinstance(path_parts, list) or any(not isinstance(item, str) for item in path_parts):
            raise ValueError
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="目标目录格式无效") from exc

    archives, designs, runs, compositions, _ = await _source_records(request)
    catalog_data = await run_in_threadpool(build_catalog, archives, designs, runs, compositions)
    unit = next((item for item in catalog_data["units"] if item["id"] == unit_id), None)
    if not unit:
        raise HTTPException(status_code=404, detail="未找到目标课程单元")

    uploads: list[tuple[str, bytes]] = []
    total_bytes = 0
    for upload in files:
        data = await upload.read()
        total_bytes += len(data)
        if total_bytes > MAX_HUB_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="单次上传总大小不能超过 360 MB")
        uploads.append((upload.filename or "未命名资料", data))

    settings = get_settings()
    try:
        record = await run_in_threadpool(load_archive, settings.course_archive_store_path, unit["archive_id"])
        updated, added = await run_in_threadpool(
            append_course_archive_files, record, uploads, settings.document_store_path, None,
        )
        layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, unit_id)
        base_folder_id = folder_id or None
        if base_folder_id:
            if not any(item["id"] == base_folder_id for item in layout.get("folders", [])):
                raise KeyError("目标文件夹已不存在")
        elif path_parts:
            layout, base_folder_id, _ = await run_in_threadpool(
                ensure_data_folder_path, layout, path_parts, None, None,
            )
        created_folders = 0
        for material in added:
            relative_parts = [part for part in material["path"].replace("\\", "/").split("/")[:-1] if part]
            target_folder_id = base_folder_id
            if relative_parts:
                layout, target_folder_id, created = await run_in_threadpool(
                    ensure_data_folder_path,
                    layout,
                    relative_parts,
                    base_folder_id,
                    None,
                )
                created_folders += created
            block_id = f"material:{unit['archive_id']}:{material['id']}:original"
            layout = await run_in_threadpool(update_block_layout, layout, block_id, None, True, target_folder_id)
        await run_in_threadpool(save_archive, settings.course_archive_store_path, updated)
        await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
        return DataHubUploadResult(
            archive_id=unit["archive_id"], unit_id=unit_id,
            material_count=len(added), folder_count=created_folders,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileExistsError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/folders", response_model=DataHubLayout, status_code=status.HTTP_201_CREATED)
async def create_folder(payload: FolderCreate, request: Request) -> DataHubLayout:
    archives, designs, runs, compositions, _ = await _source_records(request)
    catalog_data = await run_in_threadpool(build_catalog, archives, designs, runs, compositions)
    if not any(item["id"] == payload.unit_id for item in catalog_data["units"]):
        raise HTTPException(status_code=404, detail="未找到资料单元")
    settings = get_settings()
    layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, payload.unit_id)
    try:
        updated, _ = await run_in_threadpool(
            create_data_folder, layout, payload.name, payload.parent_id, payload.system_parent,
        )
        await run_in_threadpool(save_layout, settings.data_hub_store_path, updated)
        return DataHubLayout.model_validate(updated)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/folders/{folder_id}", response_model=DataHubLayout)
async def update_folder(folder_id: str, payload: FolderUpdate) -> DataHubLayout:
    settings = get_settings()
    layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
    try:
        layout = _layout_with_folder(layouts, folder_id)
        updated = await run_in_threadpool(
            update_data_folder, layout, folder_id, payload.name, payload.move, payload.parent_id, payload.system_parent,
        )
        await run_in_threadpool(save_layout, settings.data_hub_store_path, updated)
        return DataHubLayout.model_validate(updated)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/folders/{folder_id}", status_code=204)
async def remove_folder(folder_id: str, recursive: bool = Query(default=False)) -> Response:
    settings = get_settings()
    layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
    try:
        layout = _layout_with_folder(layouts, folder_id)
        if recursive:
            archive_id = layout["unit_id"].split(":", 1)[0]
            archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
            folder_paths: list[str] = []
            for nested_id in await run_in_threadpool(folder_subtree_ids, layout, folder_id):
                try:
                    source, _, relative = await run_in_threadpool(resolve_local_folder_path, archive, layout, nested_id)
                    if relative:
                        folder_paths.append(f"{source['id']}\u0000{relative}")
                except (KeyError, ValueError, FileNotFoundError):
                    continue
            if folder_paths:
                archive = await run_in_threadpool(record_local_deletions, archive, set(), folder_paths)
                await run_in_threadpool(save_archive, settings.course_archive_store_path, archive)
            updated, block_ids = await run_in_threadpool(delete_data_folder_recursive, layout, folder_id)
            original_block_ids = [block_id for block_id in block_ids if block_id.endswith(":original")]
            if original_block_ids:
                await _delete_original_blocks(layout["unit_id"], original_block_ids)
                latest = await run_in_threadpool(load_layout, settings.data_hub_store_path, layout["unit_id"])
                updated, _ = await run_in_threadpool(delete_data_folder_recursive, latest, folder_id)
        else:
            updated = await run_in_threadpool(delete_data_folder, layout, folder_id)
        await run_in_threadpool(save_layout, settings.data_hub_store_path, updated)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@router.patch("/blocks/{block_id:path}", response_model=DataHubLayout)
async def update_content_block(block_id: str, payload: DataHubBlockUpdate, request: Request) -> DataHubLayout:
    archives, designs, runs, compositions, _ = await _source_records(request)
    catalog_data = await run_in_threadpool(build_catalog, archives, designs, runs, compositions)
    block = next((item for item in catalog_data["blocks"] if item["id"] == block_id), None)
    if not block:
        raise HTTPException(status_code=404, detail="未找到资料")
    if block.get("unit_id") != payload.unit_id:
        raise HTTPException(status_code=409, detail="资料不属于当前单元，请刷新后重试")
    settings = get_settings()
    layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, payload.unit_id)
    try:
        updated = await run_in_threadpool(
            update_block_layout, layout, block_id, payload.title, payload.move, payload.folder_id,
        )
        await run_in_threadpool(save_layout, settings.data_hub_store_path, updated)
        return DataHubLayout.model_validate(updated)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blocks/move", response_model=DataHubLayout)
async def move_content_blocks(payload: DataHubBlocksMove, request: Request) -> DataHubLayout:
    archives, designs, runs, compositions, _ = await _source_records(request)
    catalog_data = await run_in_threadpool(build_catalog, archives, designs, runs, compositions)
    blocks = {item["id"]: item for item in catalog_data["blocks"]}
    if any(block_id not in blocks for block_id in payload.block_ids):
        raise HTTPException(status_code=404, detail="部分资料已不存在，请刷新后重试")
    if any(blocks[block_id].get("unit_id") != payload.unit_id for block_id in payload.block_ids):
        raise HTTPException(status_code=409, detail="只能移动当前单元中的资料")
    settings = get_settings()
    layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, payload.unit_id)
    try:
        updated = layout
        for block_id in payload.block_ids:
            updated = update_block_layout(updated, block_id, move=True, folder_id=payload.folder_id)
        await run_in_threadpool(save_layout, settings.data_hub_store_path, updated)
        return DataHubLayout.model_validate(updated)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _rescan_and_save_local_source(archive: dict, source: dict) -> tuple[dict, dict]:
    settings = get_settings()
    updated, refreshed_source, _, removed_document_ids = await run_in_threadpool(
        scan_local_source,
        source["root_path"], archive, {}, settings.document_store_path, source["id"], source["name"],
    )
    catalog_data = await run_in_threadpool(build_catalog, [updated], [], [], [])
    layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
    changed_layouts, _ = await run_in_threadpool(
        organize_source_archive, catalog_data, layouts, updated["id"], refreshed_source,
    )
    await run_in_threadpool(save_archive, settings.course_archive_store_path, updated)
    for changed_layout in changed_layouts:
        await run_in_threadpool(save_layout, settings.data_hub_store_path, changed_layout)
    for document_id in removed_document_ids:
        await run_in_threadpool(delete_document, settings.document_store_path, document_id)
    return updated, refreshed_source


@router.post("/local-sync/folder", response_model=LocalSyncResult)
async def sync_created_folder(payload: LocalFolderSyncRequest) -> LocalSyncResult:
    settings = get_settings()
    archive_id = payload.unit_id.split(":", 1)[0]
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, payload.unit_id)
        source, created = await run_in_threadpool(sync_folder_to_local, archive, layout, payload.folder_id)
        updated, refreshed_source = await _rescan_and_save_local_source(archive, source)
        return LocalSyncResult(
            archive_id=archive_id, unit_id=payload.unit_id, source_id=refreshed_source["id"],
            created_directories=created,
            message="已在本机创建对应文件夹" if created else "本机文件夹已存在，索引已刷新",
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"本机目录创建失败：{exc}") from exc


@router.post("/local-sync/uploads", response_model=LocalSyncResult)
async def sync_browser_uploads(
    unit_id: str = Form(...),
    folder_id: str = Form(...),
    browser_source_id: str = Form(...),
    root_name: str = Form(default=""),
    directories: str = Form(default="[]"),
    files: list[UploadFile] = File(default=[]),
) -> LocalSyncResult:
    settings = get_settings()
    archive_id = unit_id.split(":", 1)[0]
    try:
        raw_directories = json.loads(directories)
        if not isinstance(raw_directories, list) or any(not isinstance(item, str) for item in raw_directories):
            raise ValueError("同步目录清单格式无效")
        if len(files) > MAX_HUB_UPLOAD_FILES:
            raise ValueError(f"单次最多同步 {MAX_HUB_UPLOAD_FILES} 个文件")
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, unit_id)
        browser_source = next((item for item in archive.get("source_folders", []) if item.get("id") == browser_source_id), None)
        if not browser_source or browser_source.get("kind") != "upload":
            raise KeyError("待同步的浏览器导入记录已不存在")
        uploads: list[tuple[str, bytes]] = []
        total_bytes = 0
        for upload in files:
            data = await upload.read()
            total_bytes += len(data)
            if total_bytes > MAX_HUB_UPLOAD_BYTES:
                raise ValueError("单次同步总大小不能超过 360 MB")
            uploads.append((upload.filename or "未命名资料", data))
        source, synced_files, created_directories = await run_in_threadpool(
            sync_uploads_to_local, archive, layout, folder_id, root_name, raw_directories, uploads,
        )

        material_ids = {item["id"] for item in archive.get("materials", []) if item.get("source_folder_id") == browser_source_id}
        document_ids: list[str] = []
        if material_ids:
            archive, document_ids = await run_in_threadpool(remove_course_archive_materials, archive, material_ids)
        archive["source_folders"] = [item for item in archive.get("source_folders", []) if item.get("id") != browser_source_id]
        related_block_ids = {
            f"material:{archive_id}:{material_id}:{kind}"
            for material_id in material_ids for kind in ("original", "extracted")
        }
        layout = await run_in_threadpool(remove_blocks_from_layout, layout, related_block_ids)
        browser_roots = [item for item in layout.get("folders", []) if item.get("source_folder_id") == browser_source_id]
        for browser_root in browser_roots:
            layout, _ = await run_in_threadpool(delete_data_folder_recursive, layout, browser_root["id"])
        await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
        updated, refreshed_source = await _rescan_and_save_local_source(archive, source)
        for document_id in document_ids:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
        return LocalSyncResult(
            archive_id=updated["id"], unit_id=unit_id, source_id=refreshed_source["id"],
            synced_files=synced_files, created_directories=created_directories,
            message=f"已同步 {synced_files} 个文件到本机并刷新目录",
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="同步目录清单格式无效") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"本机文件同步失败：{exc}") from exc


@router.post("/materials/local-transfer", response_model=LocalSourceScanResult)
async def transfer_local_files(payload: LocalMaterialTransferRequest) -> LocalSourceScanResult:
    settings = get_settings()
    archive_id = payload.unit_id.split(":", 1)[0]
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
        layout = await run_in_threadpool(load_layout, settings.data_hub_store_path, payload.unit_id)
        source, _ = await run_in_threadpool(
            transfer_local_materials,
            archive,
            layout,
            payload.block_ids,
            payload.destination_folder_id,
            payload.operation,
        )
        updated, refreshed_source, changes, removed_document_ids = await run_in_threadpool(
            scan_local_source,
            source["root_path"],
            archive,
            {},
            settings.document_store_path,
            source["id"],
            source["name"],
        )
        await run_in_threadpool(save_archive, settings.course_archive_store_path, updated)
        for document_id in removed_document_ids:
            await run_in_threadpool(delete_document, settings.document_store_path, document_id)
        catalog_data = await run_in_threadpool(build_catalog, [updated], [], [], [])
        layouts = await run_in_threadpool(list_layouts, settings.data_hub_store_path)
        changed_layouts, _ = await run_in_threadpool(
            organize_source_archive, catalog_data, layouts, archive_id, refreshed_source,
        )
        for changed_layout in changed_layouts:
            await run_in_threadpool(save_layout, settings.data_hub_store_path, changed_layout)
        return LocalSourceScanResult(
            archive_id=updated["id"], archive_name=updated["name"], local_root=updated["local_root"],
            changes=changes, total_files=updated["total_files"],
            total_directories=refreshed_source.get("directory_count", 0), warnings=updated.get("warnings", []),
            source_id=refreshed_source["id"], source_name=refreshed_source["name"], source_kind="local",
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"本机文件操作失败：{exc}") from exc


@router.delete("/blocks/{block_id:path}", status_code=204)
async def remove_content_block(block_id: str, unit_id: str = Query(...)) -> Response:
    try:
        await _delete_original_blocks(unit_id, [block_id])
        return Response(status_code=204)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="原始文件已不存在") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/blocks/delete", status_code=204)
async def remove_content_blocks(payload: DataHubBlocksDelete) -> Response:
    try:
        await _delete_original_blocks(payload.unit_id, payload.block_ids)
        return Response(status_code=204)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="部分原始文件已不存在") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/archives/{archive_id}/import-folder", response_model=ImportFolderOrganizeResult)
async def organize_import_folder(archive_id: str, payload: ImportFolderOrganizeRequest, request: Request) -> ImportFolderOrganizeResult:
    settings = get_settings()
    try:
        archive = await run_in_threadpool(load_archive, settings.course_archive_store_path, archive_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到刚导入的课程目录") from exc

    _, designs, runs, compositions, layouts = await _source_records(request)
    catalog_data = await run_in_threadpool(build_catalog, [archive], designs, runs, compositions)
    try:
        changed, summary = await run_in_threadpool(organize_imported_archive, catalog_data, layouts, archive_id, payload.folder_name)
        for layout in changed:
            await run_in_threadpool(save_layout, settings.data_hub_store_path, layout)
        return ImportFolderOrganizeResult.model_validate(summary)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/compositions", response_model=CompositionList)
async def compositions() -> CompositionList:
    records = await run_in_threadpool(list_compositions, get_settings().data_hub_store_path)
    return CompositionList(items=[CompositionSummary.model_validate(composition_summary(item)) for item in records])


@router.post("/compositions", response_model=CompositionRecord, status_code=status.HTTP_201_CREATED)
async def create_output(payload: CompositionCreate) -> CompositionRecord:
    record = await run_in_threadpool(create_composition, payload.model_dump())
    await run_in_threadpool(save_composition, get_settings().data_hub_store_path, record)
    return CompositionRecord.model_validate(record)


@router.post("/compositions/import", response_model=CompositionRecord, status_code=status.HTTP_201_CREATED)
async def import_output(file: UploadFile = File(...)) -> CompositionRecord:
    try:
        data = await file.read()
        record = await run_in_threadpool(
            import_composition, file.filename or "import.txt", data, get_settings().document_store_path,
        )
        await run_in_threadpool(save_composition, get_settings().data_hub_store_path, record)
        return CompositionRecord.model_validate(record)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/compositions/{composition_id}", response_model=CompositionRecord)
async def composition(composition_id: str) -> CompositionRecord:
    try:
        record = await run_in_threadpool(load_composition, get_settings().data_hub_store_path, composition_id)
        return CompositionRecord.model_validate(record)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/compositions/{composition_id}", response_model=CompositionRecord)
async def save_output(composition_id: str, payload: CompositionUpdate) -> CompositionRecord:
    try:
        record = await run_in_threadpool(load_composition, get_settings().data_hub_store_path, composition_id)
        if record.get("version", 1) != payload.base_version:
            raise HTTPException(status_code=409, detail="成果编排已被更新，请刷新后继续编辑")
        updated = await run_in_threadpool(update_composition, record, payload.model_dump(exclude={"base_version"}))
        await run_in_threadpool(save_composition, get_settings().data_hub_store_path, updated)
        return CompositionRecord.model_validate(updated)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/compositions/{composition_id}/preview", response_class=HTMLResponse)
async def preview_output(composition_id: str) -> HTMLResponse:
    try:
        record = await run_in_threadpool(load_composition, get_settings().data_hub_store_path, composition_id)
        return HTMLResponse(await run_in_threadpool(composition_html, record))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/compositions/{composition_id}/export")
async def export_output(composition_id: str, format: str = Query(default="docx", pattern="^(docx|md|json)$")) -> Response:
    try:
        record = await run_in_threadpool(load_composition, get_settings().data_hub_store_path, composition_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if format == "docx":
        content = await run_in_threadpool(composition_docx, record)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif format == "md":
        content = (await run_in_threadpool(composition_markdown, record)).encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
    else:
        content = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
        media_type = "application/json; charset=utf-8"
    filename = f"{record['title']}.{format}"
    fallback = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or f"composition.{format}"
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}",
    })


@router.delete("/compositions/{composition_id}", status_code=204)
async def remove_output(composition_id: str) -> Response:
    try:
        await run_in_threadpool(delete_composition, get_settings().data_hub_store_path, composition_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


# ---------- 系统文件夹选择器: 弹出 Windows 原生对话框选文件夹 ----------
_PICKER_SCRIPT = Path(__file__).resolve().parents[2] / "pick_folder.py"

@router.post("/pick-folder", response_model=dict)
async def pick_folder() -> dict:
    """弹出 Windows 原生文件夹选择器, 返回用户选择的绝对路径 (取消则 canceled=True)。"""
    if not _PICKER_SCRIPT.exists():
        return {"canceled": True, "error": "picker 脚本缺失", "path": None}
    py = sys.executable if sys.executable else "python"
    try:
        proc = await run_in_threadpool(
            subprocess.run, [py, str(_PICKER_SCRIPT)], capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired:
        return {"canceled": True, "error": "选择超时", "path": None}
    except Exception as exc:  # noqa: BLE001
        return {"canceled": True, "error": str(exc)[:200], "path": None}
    path = (proc.stdout or "").strip()
    if not path:
        return {"canceled": True, "error": "未选择文件夹", "path": None}
    return {"canceled": False, "path": path}
