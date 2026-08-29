import json
import threading
from pathlib import Path
from uuid import UUID


_lock = threading.RLock()


def _path(root: Path, unit_id: str) -> Path:
    return root / f"{UUID(unit_id)}.json"


def save_material_unit(root: Path, record: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = _path(root, record["id"])
    temporary = target.with_suffix(".tmp")
    with _lock:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def load_material_unit(root: Path, unit_id: str) -> dict:
    target = _path(root, unit_id)
    if not target.exists():
        raise FileNotFoundError("未找到资料单元")
    with _lock:
        return json.loads(target.read_text(encoding="utf-8"))


def list_material_units(root: Path) -> list[dict]:
    if not root.exists():
        return []
    records: list[dict] = []
    with _lock:
        for target in root.glob("*.json"):
            try:
                records.append(json.loads(target.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
    return sorted(records, key=lambda item: item.get("updated_at", ""), reverse=True)


def delete_material_units_for_archive(root: Path, archive_id: str) -> int:
    records = list_material_units(root)
    targets = [item for item in records if item.get("archive_id") == archive_id]
    with _lock:
        for record in targets:
            target = _path(root, record["id"])
            if target.exists():
                target.unlink()
    return len(targets)


def delete_material_unit(root: Path, unit_id: str) -> None:
    target = _path(root, unit_id)
    if not target.exists():
        raise FileNotFoundError("未找到资料单元")
    with _lock:
        target.unlink()


def _task_path(root: Path, task_id: str) -> Path:
    return root / "_refine_tasks" / f"{UUID(task_id)}.json"


def save_refine_task(root: Path, record: dict) -> None:
    target = _task_path(root, record["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with _lock:
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def load_refine_task(root: Path, task_id: str) -> dict:
    target = _task_path(root, task_id)
    if not target.exists():
        raise FileNotFoundError("未找到知识大纲细化任务")
    with _lock:
        return json.loads(target.read_text(encoding="utf-8"))


def list_refine_tasks(root: Path, unit_id: str, outline_id: str = "") -> list[dict]:
    task_root = root / "_refine_tasks"
    if not task_root.exists():
        return []
    records: list[dict] = []
    with _lock:
        for target in task_root.glob("*.json"):
            try:
                record = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if record.get("unit_id") != unit_id:
                continue
            if outline_id and record.get("outline_id") != outline_id:
                continue
            records.append(record)
    return sorted(records, key=lambda item: item.get("updated_at", ""), reverse=True)


# ---------- M7: 教材研读图谱节点 (md 文件存储, 可查看/编辑) ----------
def graph_notes_dir(root: Path, unit_id: str) -> Path:
    return root / "graph_notes" / str(UUID(unit_id))


def save_graph_note(root: Path, unit_id: str, node_id: str, content_md: str, title: str) -> Path:
    """把图谱节点保存为单元下的 .md 文件(可查看/编辑)。"""
    target = graph_notes_dir(root, unit_id) / f"{node_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".md.tmp")
    with _lock:
        temporary.write_text(f"# {title}\n\n{content_md}".rstrip() + "\n", encoding="utf-8")
        temporary.replace(target)
    return target


def load_graph_note(root: Path, unit_id: str, node_id: str) -> dict | None:
    target = graph_notes_dir(root, unit_id) / f"{node_id}.md"
    if not target.exists():
        return None
    with _lock:
        content = target.read_text(encoding="utf-8")
    title = content.splitlines()[0].lstrip("# ").strip() if content else ""
    # 首行是标题, 正文去掉它
    body = "\n".join(content.splitlines()[1:]).strip()
    return {"node_id": node_id, "title": title, "content": body}


def delete_graph_note(root: Path, unit_id: str, node_id: str) -> None:
    target = graph_notes_dir(root, unit_id) / f"{node_id}.md"
    with _lock:
        if target.exists():
            target.unlink()
