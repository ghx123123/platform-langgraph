import json
import hashlib
import threading
from pathlib import Path
from uuid import UUID


_lock = threading.RLock()


def _path(root: Path, composition_id: str) -> Path:
    return root / f"{UUID(composition_id)}.json"


def save_composition(root: Path, record: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = _path(root, record["id"])
    temporary = target.with_suffix(".tmp")
    with _lock:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def load_composition(root: Path, composition_id: str) -> dict:
    target = _path(root, composition_id)
    if not target.exists():
        raise FileNotFoundError("未找到成果编排记录")
    with _lock:
        return json.loads(target.read_text(encoding="utf-8"))


def list_compositions(root: Path) -> list[dict]:
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


def delete_composition(root: Path, composition_id: str) -> None:
    target = _path(root, composition_id)
    if not target.exists():
        raise FileNotFoundError("未找到成果编排记录")
    with _lock:
        target.unlink()


def delete_compositions_for_archive(root: Path, archive_id: str) -> int:
    deleted = 0
    for record in list_compositions(root):
        if (
            record.get("archive_id") != archive_id
            and not str(record.get("unit_id") or "").startswith(f"{archive_id}:")
        ):
            continue
        target = _path(root, record["id"])
        with _lock:
            if target.exists():
                target.unlink()
                deleted += 1
    return deleted


def _layout_path(root: Path, unit_id: str) -> Path:
    digest = hashlib.sha256(unit_id.encode("utf-8")).hexdigest()
    return root / "layouts" / f"{digest}.json"


def empty_layout(unit_id: str) -> dict:
    return {"unit_id": unit_id, "folders": [], "placements": {}, "titles": {}, "updated_at": ""}


def normalize_layout(record: dict) -> dict:
    """Flatten the retired original-material system root and merge collisions."""
    result = {**empty_layout(record["unit_id"]), **record}
    folders = [dict(item) for item in result.get("folders", [])]
    for folder in folders:
        if folder.get("parent_id") is None and folder.get("system_parent") == "original":
            folder["system_parent"] = None

    placements = dict(result.get("placements", {}))
    while True:
        seen: dict[tuple[str | None, str | None, str], str] = {}
        replacements: dict[str, str] = {}
        kept: list[dict] = []
        for folder in folders:
            key = (folder.get("parent_id"), folder.get("system_parent"), folder["name"].casefold())
            canonical_id = seen.get(key)
            if canonical_id:
                replacements[folder["id"]] = canonical_id
            else:
                seen[key] = folder["id"]
                kept.append(folder)
        if not replacements:
            folders = kept
            break
        for folder in kept:
            if folder.get("parent_id") in replacements:
                folder["parent_id"] = replacements[folder["parent_id"]]
        placements = {block_id: replacements.get(folder_id, folder_id) for block_id, folder_id in placements.items()}
        folders = kept

    result["folders"] = folders
    result["placements"] = placements
    valid_ids = {item["id"] for item in folders}
    result["placements"] = {
        block_id: folder_id for block_id, folder_id in result["placements"].items() if folder_id in valid_ids
    }
    return result


def load_layout(root: Path, unit_id: str) -> dict:
    target = _layout_path(root, unit_id)
    if not target.exists():
        return empty_layout(unit_id)
    with _lock:
        record = json.loads(target.read_text(encoding="utf-8"))
    if record.get("unit_id") != unit_id:
        raise ValueError("资料目录记录与当前单元不匹配")
    return normalize_layout(record)


def list_layouts(root: Path) -> list[dict]:
    directory = root / "layouts"
    if not directory.exists():
        return []
    records: list[dict] = []
    with _lock:
        for target in directory.glob("*.json"):
            try:
                record = json.loads(target.read_text(encoding="utf-8"))
                if record.get("unit_id"):
                    records.append(normalize_layout(record))
            except (OSError, json.JSONDecodeError):
                continue
    return records


def save_layout(root: Path, record: dict) -> None:
    record = normalize_layout(record)
    target = _layout_path(root, record["unit_id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with _lock:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def delete_layouts_for_archive(root: Path, archive_id: str) -> int:
    deleted = 0
    for record in list_layouts(root):
        if not record.get("unit_id", "").startswith(f"{archive_id}:"):
            continue
        target = _layout_path(root, record["unit_id"])
        with _lock:
            if target.exists():
                target.unlink()
                deleted += 1
    return deleted
