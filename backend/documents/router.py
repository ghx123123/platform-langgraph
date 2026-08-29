import zipfile

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from backend.core.config import get_settings
from backend.documents.service import parse_document
from backend.documents.models import DocumentVisualAnalysis, DocumentVisualAnalysisList, DocumentVisualAnalysisRequest
from backend.documents.multimodal import analyze_document_page
from backend.documents.storage import (
    load_visual_analyses,
    original_path,
    persist_original,
    persist_visual_analysis,
    preview_pdf_path,
)


router = APIRouter(prefix="/api/documents", tags=["teaching-documents"])


@router.post("/parse")
async def parse(file: UploadFile = File(...)) -> dict:
    try:
        filename = file.filename or "course.txt"
        data = await file.read()
        result = await run_in_threadpool(parse_document, filename, data)
        await run_in_threadpool(
            persist_original,
            get_settings().document_store_path,
            result["document_id"],
            filename,
            data,
        )
        return result
    except (ValueError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{document_id}/preview")
async def preview(document_id: str) -> FileResponse:
    try:
        path = await run_in_threadpool(preview_pdf_path, get_settings().document_store_path, document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=f"无法生成原页预览：{exc}") from exc
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@router.get("/{document_id}/original")
async def original(document_id: str) -> FileResponse:
    try:
        path = await run_in_threadpool(original_path, get_settings().document_store_path, document_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="未找到原始课程材料") from exc
    return FileResponse(path, headers={"Content-Disposition": "inline"})


@router.get("/{document_id}/visual-analyses", response_model=DocumentVisualAnalysisList)
async def visual_analyses(document_id: str) -> DocumentVisualAnalysisList:
    try:
        items = await run_in_threadpool(load_visual_analyses, get_settings().document_store_path, document_id)
        return DocumentVisualAnalysisList(items=[DocumentVisualAnalysis.model_validate(item) for item in items])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="未找到课程材料") from exc


@router.post("/{document_id}/visual-analysis", response_model=DocumentVisualAnalysis)
async def visual_analysis(
    document_id: str,
    payload: DocumentVisualAnalysisRequest,
    request: Request,
) -> DocumentVisualAnalysis:
    try:
        pdf_path = await run_in_threadpool(preview_pdf_path, get_settings().document_store_path, document_id)
        config = request.app.state.model_settings_service.config.model_copy(deep=True)
        result = await run_in_threadpool(analyze_document_page, pdf_path, payload, config)
        if result.status == "completed":
            await run_in_threadpool(
                persist_visual_analysis,
                get_settings().document_store_path,
                document_id,
                result.model_dump(),
            )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="未找到课程材料") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
