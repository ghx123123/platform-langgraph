import shutil
import subprocess
import threading
import json
from contextlib import suppress
from pathlib import Path
from uuid import UUID


_preview_locks: dict[str, threading.Lock] = {}
_preview_locks_guard = threading.Lock()
_visual_analysis_lock = threading.Lock()


def _safe_document_id(document_id: str) -> str:
    return str(UUID(document_id))


def persist_original(root: Path, document_id: str, filename: str, data: bytes) -> Path:
    safe_id = _safe_document_id(document_id)
    suffix = Path(filename).suffix.lower()
    directory = root / safe_id
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"original{suffix}"
    target.write_bytes(data)
    return target


def original_path(root: Path, document_id: str) -> Path:
    directory = root / _safe_document_id(document_id)
    matches = [path for path in directory.glob("original.*") if path.is_file()]
    if len(matches) != 1:
        raise FileNotFoundError("未找到原始课程材料")
    return matches[0]


def delete_document(root: Path, document_id: str) -> None:
    directory = root / _safe_document_id(document_id)
    if directory.exists():
        shutil.rmtree(directory)


def _preview_lock(document_id: str) -> threading.Lock:
    with _preview_locks_guard:
        return _preview_locks.setdefault(document_id, threading.Lock())


def _libreoffice_command() -> str | None:
    command = shutil.which("soffice") or shutil.which("libreoffice")
    if command:
        return command
    for candidate in (
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _convert_with_libreoffice(source: Path, target: Path) -> None:
    command = _libreoffice_command()
    if not command:
        raise RuntimeError("LibreOffice 不可用")
    result = subprocess.run(
        [command, "--headless", "--convert-to", "pdf", "--outdir", str(target.parent), str(source)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    generated = target.parent / f"{source.stem}.pdf"
    if result.returncode != 0 or not generated.exists():
        detail = (result.stderr or result.stdout or "转换未生成 PDF").strip()
        raise RuntimeError(detail[:300])
    generated.replace(target)


def _convert_with_microsoft_office(source: Path, target: Path) -> None:
    if source.suffix.lower() not in {".docx", ".pptx"}:
        raise RuntimeError("Microsoft Office 预览仅支持 DOCX 和 PPTX")
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    application = None
    document = None
    try:
        if source.suffix.lower() == ".docx":
            application = win32com.client.DispatchEx("Word.Application")
            application.Visible = False
            application.DisplayAlerts = 0
            with suppress(Exception):
                application.AutomationSecurity = 3
            document = application.Documents.Open(str(source.resolve()), ReadOnly=True, AddToRecentFiles=False)
            document.ExportAsFixedFormat(str(target.resolve()), 17)
        else:
            application = win32com.client.DispatchEx("PowerPoint.Application")
            with suppress(Exception):
                application.AutomationSecurity = 3
            document = application.Presentations.Open(
                str(source.resolve()), ReadOnly=True, Untitled=False, WithWindow=False
            )
            document.SaveAs(str(target.resolve()), 32)
    finally:
        if document is not None:
            with suppress(Exception):
                document.Close(False) if source.suffix.lower() == ".docx" else document.Close()
        if application is not None:
            with suppress(Exception):
                application.Quit()
        pythoncom.CoUninitialize()


def preview_pdf_path(root: Path, document_id: str) -> Path:
    safe_id = _safe_document_id(document_id)
    source = original_path(root, safe_id)
    if source.suffix.lower() == ".pdf":
        return source
    if source.suffix.lower() not in {".docx", ".pptx"}:
        raise ValueError("该文件格式不支持原页预览")
    target = source.parent / "preview.pdf"
    if target.exists() and target.stat().st_size > 0:
        return target
    with _preview_lock(safe_id):
        if target.exists() and target.stat().st_size > 0:
            return target
        errors: list[str] = []
        try:
            _convert_with_libreoffice(source, target)
        except Exception as exc:
            errors.append(f"LibreOffice: {exc}")
            with suppress(FileNotFoundError):
                target.unlink()
            try:
                _convert_with_microsoft_office(source, target)
            except Exception as office_exc:
                errors.append(f"Microsoft Office: {office_exc}")
                with suppress(FileNotFoundError):
                    target.unlink()
                raise RuntimeError("；".join(errors)) from office_exc
        return target


def load_visual_analyses(root: Path, document_id: str) -> list[dict]:
    directory = root / _safe_document_id(document_id)
    path = directory / "visual-analyses.json"
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def persist_visual_analysis(root: Path, document_id: str, analysis: dict) -> None:
    directory = root / _safe_document_id(document_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "visual-analyses.json"
    with _visual_analysis_lock:
        current = load_visual_analyses(root, document_id)
        current = [item for item in current if item.get("page_number") != analysis.get("page_number")]
        current.append(analysis)
        current.sort(key=lambda item: int(item.get("page_number", 0)))
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
