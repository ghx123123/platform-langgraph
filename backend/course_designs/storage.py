import json
import threading
from pathlib import Path
from uuid import UUID


_lock = threading.RLock()


def _path(root: Path, design_id: str) -> Path:
    return root / f"{UUID(design_id)}.json"


def save_design(root: Path, record: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = _path(root, record["id"])
    temporary = target.with_suffix(".tmp")
    with _lock:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def load_design(root: Path, design_id: str) -> dict:
    target = _path(root, design_id)
    if not target.exists():
        raise FileNotFoundError("未找到课程设计记录")
    with _lock:
        return json.loads(target.read_text(encoding="utf-8"))


def list_designs(root: Path) -> list[dict]:
    if not root.exists():
        return []
    records = []
    with _lock:
        for target in root.glob("*.json"):
            try:
                records.append(json.loads(target.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return sorted(records, key=lambda item: item.get("updated_at", ""), reverse=True)


def delete_design(root: Path, design_id: str) -> None:
    target = _path(root, design_id)
    if not target.exists():
        raise FileNotFoundError("未找到课程设计记录")
    with _lock:
        target.unlink()


def delete_designs_for_archive(root: Path, archive_id: str) -> int:
    deleted = 0
    for record in list_designs(root):
        if record.get("archive_id") != archive_id:
            continue
        target = _path(root, record["id"])
        with _lock:
            if target.exists():
                target.unlink()
                deleted += 1
    return deleted
