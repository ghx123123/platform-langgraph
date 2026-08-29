import json
import threading
from pathlib import Path
from uuid import UUID


_lock = threading.RLock()


def _safe_id(archive_id: str) -> str:
    return str(UUID(archive_id))


def _path(root: Path, archive_id: str) -> Path:
    return root / f"{_safe_id(archive_id)}.json"


def save_archive(root: Path, record: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = _path(root, record["id"])
    temporary = target.with_suffix(".tmp")
    payload = json.dumps(record, ensure_ascii=False, indent=2)
    with _lock:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(target)


def load_archive(root: Path, archive_id: str) -> dict:
    target = _path(root, archive_id)
    if not target.exists():
        raise FileNotFoundError("未找到学期资料库")
    with _lock:
        return json.loads(target.read_text(encoding="utf-8"))


def list_archives(root: Path) -> list[dict]:
    if not root.exists():
        return []
    records: list[dict] = []
    with _lock:
        for target in root.glob("*.json"):
            try:
                records.append(json.loads(target.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return records


def delete_archive(root: Path, archive_id: str) -> None:
    target = _path(root, archive_id)
    if not target.exists():
        raise FileNotFoundError("未找到学期资料库")
    with _lock:
        target.unlink()
