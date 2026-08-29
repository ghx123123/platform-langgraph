from pathlib import Path
from uuid import uuid4

from backend.documents import storage


def test_pdf_original_is_used_as_page_preview(tmp_path: Path):
    document_id = str(uuid4())
    pdf = b"%PDF-1.4\n%%EOF"

    original = storage.persist_original(tmp_path, document_id, "lesson.pdf", pdf)

    assert original.read_bytes() == pdf
    assert storage.original_path(tmp_path, document_id) == original
    assert storage.preview_pdf_path(tmp_path, document_id) == original


def test_office_preview_is_converted_once_and_cached(tmp_path: Path, monkeypatch):
    document_id = str(uuid4())
    storage.persist_original(tmp_path, document_id, "lesson.docx", b"docx-data")
    calls: list[Path] = []

    def convert(source: Path, target: Path) -> None:
        calls.append(source)
        target.write_bytes(b"%PDF-1.4\npreview\n%%EOF")

    monkeypatch.setattr(storage, "_convert_with_libreoffice", convert)

    first = storage.preview_pdf_path(tmp_path, document_id)
    second = storage.preview_pdf_path(tmp_path, document_id)

    assert first == second
    assert first.read_bytes().startswith(b"%PDF")
    assert len(calls) == 1
