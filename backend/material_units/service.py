import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4


SYLLABUS_CATEGORY_LABELS = {
    "objective": "课程目标",
    "knowledge": "知识要求",
    "key_point": "重点",
    "difficult_point": "难点",
    "practice": "实践要求",
    "assessment": "考核要求",
}
SYLLABUS_CATEGORY_PATTERNS = {
    "difficult_point": ("难点", "困难", "易错"),
    "key_point": ("重点", "关键", "核心"),
    "practice": ("实践", "实验", "实训", "操作", "项目", "上机"),
    "assessment": ("考核", "评价", "考试", "成绩", "达成度"),
    "objective": ("目标", "素养", "能力目标", "课程目标"),
    "knowledge": ("知识", "内容", "要求", "掌握", "理解", "熟悉", "了解"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _summary_text(document: dict, fallback: str) -> str:
    raw = re.sub(r"\s+", " ", str(document.get("raw_text") or "")).strip()
    if not raw:
        return fallback
    sentence = re.split(r"(?<=[。！？!?])\s*", raw[:900], maxsplit=3)
    summary = "".join(sentence[:2]).strip()
    return (summary or raw[:320])[:420]


def _knowledge_points(document: dict) -> list[str]:
    values: list[str] = []
    for item in document.get("knowledge_points") or []:
        title = str(item.get("title") if isinstance(item, dict) else item).strip()
        if title and title not in values:
            values.append(title)
    return values[:12]


_CHINESE_INDEX = "一二三四五六七八九十"


def _clean_outline_title(value: object) -> str:
    title = re.sub(r"\s+", " ", str(value or "")).strip(" .．…·-—")
    title = re.sub(r"^(第\s*[0-9一二三四五六七八九十]+\s*章)\s*", r"\1 ", title)
    title = re.sub(r"^(第\s*[0-9一二三四五六七八九十]+\s*节)\s*", r"\1 ", title)
    if re.match(rf"^第\s*[0-9{_CHINESE_INDEX}]+\s*章", title):
        title = re.sub(r"[.．…·\s]*\d{1,4}$", "", title).strip(" .．…·-—")
    return title.strip()


def _preview_subheadings(preview: object) -> list[str]:
    value = re.sub(r"\s+", " ", str(preview or "")).strip()
    matches = re.findall(
        rf"(?:^|[。；;])\s*([{_CHINESE_INDEX}]、[^。；;]{{2,34}}?)(?=(?:[{_CHINESE_INDEX}]、)|[。；;]|$)",
        value,
    )
    return [_clean_outline_title(item) for item in matches]


def _textbook_outline_candidates(document: dict) -> list[dict]:
    sections = [dict(item) for item in document.get("sections") or [] if isinstance(item, dict)]
    candidates: list[dict] = []
    index = 0
    pending_heading_tail = ""
    while index < len(sections):
        section = sections[index]
        title = _clean_outline_title(section.get("title"))
        preview = str(section.get("preview") or "").strip()
        chapter_match = re.match(rf"^第\s*[0-9{_CHINESE_INDEX}]+\s*章(?:\s|$)", title)
        if chapter_match:
            fragments: list[str] = []
            if re.fullmatch(rf"第\s*[0-9{_CHINESE_INDEX}]+\s*章", title):
                lookahead = index + 1
                while lookahead < min(len(sections), index + 3):
                    fragment = _clean_outline_title(sections[lookahead].get("title"))
                    if not re.fullmatch(r"[\u4e00-\u9fff]{2,14}", fragment):
                        break
                    fragments.append(fragment)
                    lookahead += 1
                if fragments:
                    title = f"{title} {''.join(fragments)}"
                    fragment_preview = str(sections[lookahead - 1].get("preview") or "").strip()
                    if re.fullmatch(r"[\u4e00-\u9fff]{1,2}", fragment_preview):
                        pending_heading_tail = fragment_preview
                    index = lookahead - 1
            candidates.append({**section, "title": title, "level": 1})
        elif re.match(rf"^第\s*[0-9{_CHINESE_INDEX}]+\s*节(?:\s|$)", title):
            if pending_heading_tail and re.search(r"[\u4e00-\u9fff]$", title):
                title += pending_heading_tail
            pending_heading_tail = ""
            if re.fullmatch(rf"第\s*[0-9{_CHINESE_INDEX}]+\s*节(?:\s+[\u4e00-\u9fff])?", title):
                first_token = re.split(r"[\s，。；;]", preview, maxsplit=1)[0].strip()
                if re.fullmatch(r"[\u4e00-\u9fff]{1,20}", first_token):
                    section_prefix = re.match(rf"^(第\s*[0-9{_CHINESE_INDEX}]+\s*节)\s*(.*)$", title)
                    suffix = section_prefix.group(2) if section_prefix else ""
                    title = f"{section_prefix.group(1)} {suffix}{first_token}" if section_prefix else f"{title} {first_token}"
            candidates.append({**section, "title": title, "level": 2})
            candidates.extend({
                "id": f"{section.get('id') or index}-sub-{sub_index}",
                "title": subheading,
                "level": 3,
                "preview": preview,
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end"),
            } for sub_index, subheading in enumerate(_preview_subheadings(preview)))
        elif re.match(r"^\d+(?:\.\d+){1,3}(?![\d.])", title):
            candidates.append(section)
        index += 1
    if candidates:
        return candidates
    knowledge = [
        {
            "id": f"knowledge-{item_index}",
            "title": item.get("title") if isinstance(item, dict) else str(item),
            "preview": item.get("description", "") if isinstance(item, dict) else "",
        }
        for item_index, item in enumerate(document.get("knowledge_points") or [])
    ]
    if knowledge:
        return knowledge
    heading_pattern = re.compile(
        rf"(?m)^\s*((?:第\s*[0-9{_CHINESE_INDEX}]+\s*[章节]|\d+(?:\.\d+){{1,2}})(?:\s+|、)[^\n。；]{{2,100}})\s*$"
    )
    return [
        {"id": f"raw-{item_index}", "title": match.group(1).strip(), "preview": ""}
        for item_index, match in enumerate(heading_pattern.finditer(str(document.get("raw_text") or "")))
    ]


def _display_textbook_outline(document: dict) -> list[dict]:
    outline: list[dict] = []
    seen_titles: set[str] = set()
    for section in _textbook_outline_candidates(document):
        title = _clean_outline_title(section.get("title"))
        if not title or title == "文档导言" or not re.match(
            rf"^(?:第\s*[0-9{_CHINESE_INDEX}]+\s*[章节]|[{_CHINESE_INDEX}]、|\d+(?:\.\d+){{1,2}}(?![\d.]))",
            title,
        ):
            continue
        normalized_title = re.sub(r"\s+", "", title)
        if normalized_title in seen_titles:
            continue
        seen_titles.add(normalized_title)
        number_match = re.match(r"^(\d+(?:\.\d+){1,2})(?![\d.])", title)
        level = (
            1
            if re.match(rf"^第\s*[0-9{_CHINESE_INDEX}]+\s*章", title)
            else min(3, number_match.group(1).count(".") + 1 if number_match else int(section.get("level") or 2))
        )
        outline.append({**section, "title": title, "level": level})
    return outline


def build_material_unit_file(material: dict, document: dict | None) -> dict:
    document = document or {}
    report = document.get("extraction_report") or {}
    knowledge_points = _knowledge_points(document)
    if material.get("category") == "textbook":
        cleaned_outline = _display_textbook_outline(document)
        if cleaned_outline:
            knowledge_points = [item["title"] for item in cleaned_outline[:12]]
    return {
        "material_id": material["id"],
        "name": material["name"],
        "path": material.get("path", material["name"]),
        "category": material.get("category", "other"),
        "extension": material.get("extension", ""),
        "document_id": material.get("document_id"),
        "preview_available": bool(material.get("preview_available")),
        "parse_status": material.get("parse_status", "metadata_only"),
        "parse_message": material.get("parse_message", ""),
        "character_count": int(material.get("character_count") or document.get("character_count") or 0),
        "summary": _summary_text(document, material.get("excerpt", "")),
        "section_count": len(document.get("sections") or []),
        "knowledge_points": knowledge_points,
        "extraction_engine": str(report.get("engine") or ""),
        "quality_level": str(report.get("quality_level") or ""),
    }


def build_link(unit: dict) -> dict:
    return {
        "unit_id": unit["id"], "title": unit.get("title", "资料单元"),
        "archive_id": unit.get("archive_id", ""), "archive_name": unit.get("archive_name", ""),
        "material_count": int(unit.get("material_count") or len(unit.get("files") or [])),
        "files": [{**item, "archive_id": item.get("archive_id") or unit.get("archive_id"), "source_unit_id": unit["id"]} for item in unit.get("files") or []],
    }


def material_unit_summary(record: dict) -> dict:
    keys = (
        "id", "archive_id", "archive_name", "title", "material_count", "parsed_count",
        "total_characters", "overview", "key_points", "created_at", "updated_at", "linked_unit_count", "source_category_counts",
    )
    result = {key: record.get(key) for key in keys}
    result["linked_unit_count"] = int(record.get("linked_unit_count") or len(record.get("linked_units") or []))
    result["source_category_counts"] = record.get("source_category_counts") or dict(Counter(item.get("category", "other") for item in record.get("files") or []))
    return result


def create_or_update_material_unit(
    archive: dict,
    title: str,
    material_ids: list[str],
    existing: dict | None = None,
) -> dict:
    known = {item["id"]: item for item in archive.get("materials", [])}
    ordered_ids = list(dict.fromkeys([*(existing or {}).get("material_ids", []), *material_ids]))
    missing = [item_id for item_id in ordered_ids if item_id not in known]
    if missing:
        raise KeyError("部分课程资料已不存在，请刷新课程资料库后重新选择")
    documents = archive.get("_documents", {})
    files = [build_material_unit_file(known[item_id], documents.get(item_id)) for item_id in ordered_ids]
    parsed = [item for item in files if item["parse_status"] == "parsed"]
    points = [point for item in parsed for point in item["knowledge_points"]]
    key_points = [point for point, _ in Counter(points).most_common(12)]
    formats = [item["extension"].lstrip(".").upper() or "FILE" for item in files]
    parsed_names = "、".join(item["name"] for item in parsed[:3])
    overview = (
        f"本单元包含 {len(files)} 份资料，已完成 {len(parsed)} 份内容提取。"
        f"资料格式包括 {'、'.join(dict.fromkeys(formats)) or '未知格式'}。"
        + (f"已分析文件：{parsed_names}{'等' if len(parsed) > 3 else ''}。" if parsed else "当前没有可用的正文分析结果。")
    )
    now = utc_now()
    linked_units = list((existing or {}).get("linked_units") or [])
    category_counts = Counter(item["category"] for item in files)
    return {
        "id": (existing or {}).get("id") or str(uuid4()),
        "archive_id": archive["id"],
        "archive_name": archive.get("course_title") or archive.get("name") or "课程资料库",
        "title": title.strip(),
        "material_ids": ordered_ids,
        "files": files,
        "linked_units": linked_units,
        "material_references": list((existing or {}).get("material_references") or []),
        "knowledge_outlines": list((existing or {}).get("knowledge_outlines") or []),
        "initial_outline": (existing or {}).get("initial_outline"),
        "scope_selection": (existing or {}).get("scope_selection") or {},
        "linked_unit_count": len(linked_units),
        "source_category_counts": dict(category_counts),
        "material_count": len(files),
        "parsed_count": len(parsed),
        "total_characters": sum(item["character_count"] for item in files),
        "overview": overview,
        "key_points": key_points,
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }


def merge_material_units(target: dict, sources: list[dict], title: str | None = None) -> dict:
    """Merge same-archive material snapshots into the target and keep cross-archive sources as links."""
    links = list(target.get("linked_units") or [])
    local_ids = list(target.get("material_ids") or [])
    files = list(target.get("files") or [])
    for source in sources:
        if source.get("archive_id") == target.get("archive_id"):
            for material_id in source.get("material_ids") or []:
                if material_id not in local_ids:
                    local_ids.append(material_id)
            existing_file_ids = {item.get("material_id") for item in files}
            files.extend({**item, "archive_id": target.get("archive_id")} for item in source.get("files") or [] if item.get("material_id") not in existing_file_ids)
        elif source.get("id") not in {item.get("unit_id") for item in links}:
            links.append(build_link(source))
            existing_file_ids = {item.get("material_id") for item in files}
            files.extend({**item, "archive_id": source.get("archive_id"), "source_unit_id": source.get("id")} for item in source.get("files") or [] if item.get("material_id") not in existing_file_ids)
    files = list({item.get("material_id"): item for item in files}.values())
    parsed = [item for item in files if item.get("parse_status") == "parsed"]
    points = list(dict.fromkeys(point for item in files for point in item.get("knowledge_points") or []))[:12]
    categories = dict(Counter(item.get("category", "other") for item in files))
    now = utc_now()
    return {
        **target,
        "title": (title or target.get("title") or "合并资料单元").strip(),
        "material_ids": local_ids,
        "files": files,
        "linked_units": links,
        "linked_unit_count": len(links),
        "material_count": len(files),
        "parsed_count": len(parsed),
        "total_characters": sum(int(item.get("character_count") or 0) for item in files),
        "key_points": points,
        "source_category_counts": categories,
        "overview": f"本单元包含 {len(files)} 份资料，已完成 {len(parsed)} 份内容提取，并关联 {len(links)} 个资料单元。",
        "updated_at": now,
    }


def _scope_sources(unit: dict, linked: list[dict]) -> list[dict]:
    sources = [unit, *linked]
    for reference in unit.get("material_references") or []:
        sources.append({
            "id": reference.get("source_unit_id"),
            "title": reference.get("source_unit_title") or "关联资料",
            "archive_id": reference.get("archive_id"),
            "archive_name": reference.get("archive_name", ""),
            "material_ids": [reference.get("material_id")],
        })
    merged: dict[tuple[str, str], dict] = {}
    for source in sources:
        key = (str(source.get("id") or ""), str(source.get("archive_id") or ""))
        if key not in merged:
            merged[key] = {**source, "material_ids": list(source.get("material_ids") or [])}
        else:
            merged[key]["material_ids"] = list(dict.fromkeys([
                *merged[key].get("material_ids", []), *source.get("material_ids", []),
            ]))
    return list(merged.values())


def build_scope_options(unit: dict, linked: list[dict], archives: dict[str, dict]) -> dict:
    teaching_items: list[dict] = []
    syllabus_items: list[dict] = []
    textbook_outline: list[dict] = []
    sources = _scope_sources(unit, linked)
    for source in sources:
        archive = archives.get(source.get("archive_id"), {})
        source_name = source.get("title", "资料单元")
        allowed_ids = set(source.get("material_ids") or [])
        material_map = {item.get("id"): item for item in archive.get("materials") or []}
        for item in archive.get("schedule") or []:
            if item.get("source_material_id") not in allowed_ids:
                continue
            content = item.get("content", "")
            lesson_match = re.match(r"\s*(\d{1,3})\b", content)
            lesson_title = f"第{lesson_match.group(1)}次课" if lesson_match else item.get("label")
            teaching_items.append({
                "id": f"schedule:{source.get('id')}:{item.get('id')}", "content": item.get("content", ""),
                "title": lesson_title or item.get("content", "")[:50], "source_material_id": item.get("source_material_id", ""),
                "source_unit_id": source.get("id", ""), "source_name": source_name,
                "document_id": material_map.get(item.get("source_material_id"), {}).get("document_id"),
                "source_hash": material_map.get(item.get("source_material_id"), {}).get("sha256"),
                "locator": f"schedule:{item.get('id')}",
            })
        for material in archive.get("materials") or []:
            if material.get("id") not in allowed_ids or material.get("category") != "syllabus":
                continue
            document = archive.get("_documents", {}).get(material.get("id"), {})
            for index, section in enumerate(document.get("sections") or []):
                value = re.sub(r"\s+", " ", str(section.get("preview") or "")).strip()
                title = re.sub(r"\s+", " ", str(section.get("title") or "")).strip()
                if title and title != "文档导言":
                    # 稳定 ID: 基于标题哈希(与教材一致), 解析后 section 编号漂移不影响已选
                    stable_key = hashlib.sha256(title.encode("utf-8")).hexdigest()[:10]
                    syllabus_items.append({
                        "id": f"syllabus:{source.get('id')}:{material.get('id')}:{stable_key}", "title": title[:80], "content": value[:420] or title,
                        "source_material_id": material.get("id", ""), "source_unit_id": source.get("id", ""), "source_name": source_name,
                        "document_id": material.get("document_id"), "source_hash": material.get("sha256"),
                        "locator": f"section:{section.get('id') or index}",
                    })
        for material in archive.get("materials") or []:
            if material.get("id") not in allowed_ids or material.get("category") != "textbook":
                continue
            document = archive.get("_documents", {}).get(material.get("id"), {})
            for index, section in enumerate(_display_textbook_outline(document)):
                title = section["title"]
                # 稳定 ID: 基于"章节编号"(数字段落/中文序号), 而非完整标题全文——
                # 不同解析引擎对标题空格/标点处理不同, 但编号(1.6.1)跨引擎稳定。
                # 无编号的标题回退到归一化标题哈希。
                number_match = re.match(r"^(第\s*[0-9一二三四五六七八九十百]+\s*[章节篇单元]|\d+(?:\.\d+){1,3}|[一二三四五六七八九十]+、|\(\d+\))", title)
                if number_match:
                    stable_key = re.sub(r"\s+", "", number_match.group(1))
                else:
                    stable_key = re.sub(r"[^0-9a-zA-Z一-鿿]", "", title).lower()[:40]
                node_id = (
                    f"outline:{source.get('id')}:{material.get('id')}:"
                    f"{hashlib.sha256(stable_key.encode('utf-8')).hexdigest()[:10]}"
                )
                textbook_outline.append({
                    "id": node_id,
                    "title": title, "level": section["level"],
                    "preview": section.get("preview", ""), "source_material_id": material.get("id", ""),
                    "source_unit_id": source.get("id", ""), "source_name": source_name,
                    "document_id": material.get("document_id"), "source_hash": material.get("sha256"),
                    "locator": f"section:{section.get('id') or index}",
                })
    return {"unit_id": unit["id"], "course_title": unit.get("archive_name", "课程"), "teaching_items": teaching_items[:120], "syllabus_items": syllabus_items[:120], "textbook_outline": textbook_outline[:300]}


def build_initial_outline(options: dict, payload: dict) -> dict:
    teaching = {item["id"]: item for item in options.get("teaching_items", [])}
    syllabus = {item["id"]: item for item in options.get("syllabus_items", [])}
    outline = {item["id"]: item for item in options.get("textbook_outline", [])}
    selected_teaching = [teaching[item_id] for item_id in payload.get("teaching_item_ids", []) if item_id in teaching]
    selected_syllabus = [syllabus[item_id] for item_id in payload.get("syllabus_item_ids", []) if item_id in syllabus]
    selected_nodes = [outline[item_id] for item_id in payload.get("outline_node_ids", []) if item_id in outline]
    sections = [item["title"] for item in selected_nodes]
    session = "、".join(item["title"] for item in selected_teaching) or "待确定讲次"
    objective = "；".join(item["content"] for item in selected_syllabus[:3]) or "根据选定教材章节明确知识目标、能力目标与课堂任务。"
    scope_summary = "；".join(sections[:8]) or "尚未选择教材章节"
    return {"title": payload.get("title", "").strip() or f"{options.get('course_title', '课程')} · {session}", "session": session, "objective": objective, "scope_summary": scope_summary, "sections": sections}


def build_synthesize_context(options: dict, payload: dict, accessible: dict[str, dict]) -> dict:
    """整合模式上下文: 收集所选材料摘要 + 教师提示词; 供 LLM 整合为连贯知识大纲。"""
    teaching = {item["id"]: item for item in options.get("teaching_items", [])}
    syllabus = {item["id"]: item for item in options.get("syllabus_items", [])}
    outline = {item["id"]: item for item in options.get("textbook_outline", [])}
    selected_teaching = [teaching[item_id] for item_id in payload.get("teaching_item_ids", []) if item_id in teaching]
    selected_syllabus = [syllabus[item_id] for item_id in payload.get("syllabus_item_ids", []) if item_id in syllabus]
    selected_nodes = [outline[item_id] for item_id in payload.get("outline_node_ids", []) if item_id in outline]

    # 材料正文摘要 (有材料模式): 从 accessible 读 raw_text 前段
    material_excerpts: list[dict] = []
    for node in selected_nodes:
        mid = node.get("source_material_id")
        if not mid or mid not in accessible:
            continue
        doc = accessible[mid].get("document") or {}
        excerpt = _summary_text(doc, str(node.get("preview") or node.get("title") or ""))
        if excerpt:
            material_excerpts.append({"material": node.get("title", mid), "excerpt": excerpt[:600]})

    session = "、".join(item["title"] for item in selected_teaching) or "待确定讲次"
    objective = "；".join(item["content"] for item in selected_syllabus[:3]) or "根据选定教材章节明确知识目标、能力目标与课堂任务。"
    sections = [item["title"] for item in selected_nodes]
    return {
        "title": payload.get("title", "").strip() or f"{options.get('course_title', '课程')} · {session}",
        "session": session,
        "objective": objective,
        "sections": sections[:24],
        "material_excerpts": material_excerpts,
        "teacher_instruction": payload.get("teacher_instruction", ""),
        "mode": "material" if material_excerpts else ("instruction" if payload.get("teacher_instruction", "").strip() else "empty"),
    }


def build_file_references(source: dict, material_ids: list[str]) -> list[dict]:
    files = {item.get("material_id"): item for item in source.get("files") or []}
    missing = [material_id for material_id in material_ids if material_id not in files]
    if missing:
        raise KeyError("部分关联文件不属于来源资料单元")
    return [{
        "id": str(uuid4()),
        "source_unit_id": source["id"],
        "source_unit_title": source.get("title", "资料单元"),
        "archive_id": source.get("archive_id", ""),
        "archive_name": source.get("archive_name", ""),
        "material_id": material_id,
        "file": {
            **files[material_id],
            "archive_id": files[material_id].get("archive_id") or source.get("archive_id"),
            "source_unit_id": source["id"],
        },
    } for material_id in dict.fromkeys(material_ids)]


def _normalize_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value or "").lower()


def _chapter_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    normalized = value or ""
    for match in re.finditer(r"第\s*([一二三四五六七八九十百\d]+)\s*[章节讲]", normalized):
        tokens.add(f"chapter:{match.group(1)}")
    for match in re.finditer(r"(?<!\d)(\d+(?:\.\d+){1,2})(?!\d)", normalized):
        number = match.group(1)
        tokens.add(f"section:{number}")
        tokens.add(f"chapter:{number.split('.')[0]}")
    return tokens


def _text_tokens(value: str) -> set[str]:
    normalized = _normalize_text(value)
    latin = set(re.findall(r"[a-zA-Z]{2,}|\d+(?:\.\d+)+", value or ""))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    grams = {chinese[index:index + size] for size in (2, 3) for index in range(max(0, len(chinese) - size + 1))}
    stop = {"课程", "教学", "学生", "要求", "内容", "掌握", "理解", "熟悉", "了解", "能够", "进行"}
    return {token.lower() for token in latin | grams if token and token not in stop}


def classify_syllabus_requirement(title: str, content: str) -> str:
    text = f"{title} {content}"
    for category in ("difficult_point", "key_point", "practice", "assessment", "objective", "knowledge"):
        if any(pattern in text for pattern in SYLLABUS_CATEGORY_PATTERNS[category]):
            return category
    return "knowledge"


def _syllabus_similarity(session_text: str, candidate_text: str) -> tuple[float, str]:
    session_tokens = _text_tokens(session_text)
    candidate_tokens = _text_tokens(candidate_text)
    common = session_tokens & candidate_tokens
    union = session_tokens | candidate_tokens
    token_score = len(common) / max(1, len(session_tokens))
    jaccard = len(common) / max(1, len(union))
    chapter_overlap = _chapter_tokens(session_text) & _chapter_tokens(candidate_text)
    sequence = SequenceMatcher(None, _normalize_text(session_text), _normalize_text(candidate_text)).ratio()
    score = min(1.0, token_score * 0.5 + jaccard * 0.2 + sequence * 0.15 + (0.35 if chapter_overlap else 0.0))
    reasons: list[str] = []
    if chapter_overlap:
        reasons.append("章节编号一致")
    if common:
        reasons.append(f"共同关键词：{'、'.join(sorted(common, key=len, reverse=True)[:4])}")
    if not reasons:
        reasons.append("文本主题相似")
    return score, "；".join(reasons)


def match_syllabus_requirements(
    options: dict,
    teaching_item_ids: list[str],
    limit_per_category: int = 4,
    model_matches: list[dict] | None = None,
) -> dict:
    teaching_map = {item["id"]: item for item in options.get("teaching_items") or []}
    selected = [teaching_map[item_id] for item_id in teaching_item_ids if item_id in teaching_map]
    if not selected:
        raise KeyError("未找到选定讲次")
    session_text = "\n".join(f"{item.get('title', '')} {item.get('content', '')}" for item in selected)
    model_map = {
        str(item.get("id")): item for item in model_matches or []
        if isinstance(item, dict) and item.get("id")
    }
    candidates: list[dict] = []
    for item in options.get("syllabus_items") or []:
        score, reason = _syllabus_similarity(session_text, f"{item.get('title', '')} {item.get('content', '')}")
        category = classify_syllabus_requirement(item.get("title", ""), item.get("content", ""))
        model_item = model_map.get(item["id"])
        if model_item:
            try:
                model_score = max(0.0, min(1.0, float(model_item.get("score", 0))))
            except (TypeError, ValueError):
                model_score = 0.0
            score = score * 0.65 + model_score * 0.35
            model_category = model_item.get("category")
            if model_category in SYLLABUS_CATEGORY_LABELS:
                category = model_category
            if model_item.get("reason"):
                reason = f"{reason}；模型判断：{str(model_item['reason'])[:160]}"
        candidates.append({
            "id": item["id"], "category": category, "category_label": SYLLABUS_CATEGORY_LABELS[category],
            "title": item.get("title", ""), "content": item.get("content", ""),
            "score": round(score, 4), "reason": reason, "recommended": score >= 0.3,
            "evidence": _scope_evidence(item, "syllabus", item.get("content") or item.get("title") or "大纲要求"),
        })
    selected_matches: list[dict] = []
    for category in SYLLABUS_CATEGORY_LABELS:
        ranked = sorted((item for item in candidates if item["category"] == category), key=lambda item: item["score"], reverse=True)
        relevant = [item for item in ranked if item["score"] >= 0.12][:limit_per_category]
        selected_matches.extend(relevant)
    selected_matches.sort(key=lambda item: item["score"], reverse=True)
    return {
        "unit_id": options["unit_id"], "teaching_items": selected, "matches": selected_matches,
        "total_candidates": len(candidates), "matching_method": "hybrid" if model_matches else "deterministic",
        "model_used": bool(model_matches),
    }


def _scope_evidence(item: dict, source_type: str, quote: str) -> dict:
    return {
        "source_type": source_type,
        "material_id": item.get("source_material_id", ""),
        "source_unit_id": item.get("source_unit_id", ""),
        "document_id": item.get("document_id"),
        "source_hash": item.get("source_hash"),
        "locator": item.get("locator", ""),
        "quote": re.sub(r"\s+", " ", quote).strip()[:1200] or "来源内容",
        "label": item.get("source_name", ""),
    }


def create_knowledge_outline(
    unit_id: str,
    options: dict,
    payload: dict,
    requirement_matches: list[dict],
) -> dict:
    teaching_map = {item["id"]: item for item in options.get("teaching_items") or []}
    syllabus_map = {item["id"]: item for item in options.get("syllabus_items") or []}
    textbook_map = {item["id"]: item for item in options.get("textbook_outline") or []}
    # 容错: 失效/过期范围选项不再整体报错, 静默跳过.
    # 保留匹配项; 只有用户明确选择了却全部失效时才提示刷新重选(极端情况, 前端已对齐则不会发生).
    def _keep_valid(ids: list[str] | None, valid_map: dict[str, object]) -> list[str]:
        # 教师自定义要求(id=custom-*) 不在 syllabus_map, 但应放行(它们由 requirements 携带)
        return [i for i in (ids or []) if i in valid_map or i.startswith("custom-")]
    payload_teaching = _keep_valid(payload.get("teaching_item_ids", []), teaching_map)
    payload_syllabus = _keep_valid(payload.get("syllabus_item_ids", []), syllabus_map)
    payload_textbook = _keep_valid(payload.get("outline_node_ids", []), textbook_map)
    if payload.get("teaching_item_ids") and not payload_teaching:
        raise KeyError("所选的讲次已失效，请刷新后重新选择")
    if payload.get("syllabus_item_ids") and not payload_syllabus:
        raise KeyError("所选的教纲要求已失效，请刷新后重新选择")
    if payload.get("outline_node_ids") and not payload_textbook:
        raise KeyError("所选的教材范围已失效，请刷新后重新选择")
    selected_teaching = [teaching_map[item_id] for item_id in payload_teaching]
    if not selected_teaching:
        raise KeyError("未找到选定讲次")
    selected_syllabus_ids = list(dict.fromkeys(payload_syllabus or [item["id"] for item in requirement_matches if item.get("recommended")]))
    selected_requirements = [item for item in requirement_matches if item.get("id") in selected_syllabus_ids]
    selected_textbook = [textbook_map[item_id] for item_id in payload_textbook]
    custom_nodes = payload.get("nodes") or []
    if custom_nodes:
        nodes = custom_nodes
    else:
        nodes = [{
            "id": str(uuid4()), "parent_id": None, "level": item.get("level", 1), "title": item["title"],
            "description": item.get("preview", ""), "is_key_point": False, "is_difficult_point": False,
            "teacher_note": "", "evidence": [_scope_evidence(item, "textbook", item.get("preview") or item["title"])],
        } for item in selected_textbook]
        if not nodes:
            for requirement in selected_requirements:
                # 教师自定义/补充要求: 仅作为选中依据(requirements), 不生成大纲节点
                if requirement.get("custom"):
                    continue
                nodes.append({
                    "id": str(uuid4()), "parent_id": None, "level": 1, "title": requirement["title"],
                    "description": requirement["content"], "is_key_point": requirement["category"] == "key_point",
                    "is_difficult_point": requirement["category"] == "difficult_point", "teacher_note": "",
                    "evidence": [requirement["evidence"]],
                })
        if not nodes and payload.get("teacher_instruction", "").strip():
            nodes = [{
                "id": str(uuid4()), "parent_id": None, "level": 1,
                "title": payload["teacher_instruction"].strip()[:120], "description": "",
                "is_key_point": False, "is_difficult_point": False, "teacher_note": payload["teacher_instruction"].strip(),
                "evidence": [{"source_type": "teacher", "quote": payload["teacher_instruction"].strip(), "label": "教师补充"}],
            }]
    if not nodes:
        raise ValueError("至少选择一个教材章节、大纲要求，或提供教师明确补充的知识点")
    session_title = "、".join(item.get("title", "") for item in selected_teaching)
    source_ids = list(dict.fromkeys([
        *[item.get("source_material_id", "") for item in selected_teaching],
        *[item.get("source_material_id", "") for item in selected_textbook],
        *[item.get("evidence", {}).get("material_id", "") for item in selected_requirements],
    ]))
    now = utc_now()
    return {
        "id": str(uuid4()), "unit_id": unit_id, "version": 1, "status": payload.get("status", "draft"),
        "title": payload.get("title", "").strip() or f"{options.get('course_title', '课程')} · {session_title}知识大纲",
        "selected_session_ids": [item["id"] for item in selected_teaching],
        "selected_syllabus_item_ids": selected_syllabus_ids,
        "selected_textbook_node_ids": [item["id"] for item in selected_textbook],
        "requirements": selected_requirements, "nodes": nodes,
        "source_material_ids": [item for item in source_ids if item],
        "teacher_instruction": payload.get("teacher_instruction", ""), "change_summary": "创建知识大纲",
        "based_on_version": None, "created_at": now, "updated_at": now,
    }


def next_outline_version(base: dict, changes: dict) -> dict:
    now = utc_now()
    return {
        **base,
        "version": int(base.get("version") or 0) + 1,
        "title": changes.get("title") if changes.get("title") is not None else base.get("title"),
        "status": changes.get("status") if changes.get("status") is not None else base.get("status", "draft"),
        "nodes": changes.get("nodes") if changes.get("nodes") is not None else base.get("nodes", []),
        "source_material_ids": changes.get("source_material_ids") if changes.get("source_material_ids") is not None else base.get("source_material_ids", []),
        "teacher_instruction": changes.get("teacher_instruction") if changes.get("teacher_instruction") is not None else base.get("teacher_instruction", ""),
        "change_summary": changes.get("change_summary") or "教师编辑",
        "based_on_version": int(base.get("version") or 1), "created_at": now, "updated_at": now,
    }


def accessible_material_documents(unit: dict, linked: list[dict], archives: dict[str, dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for source in _scope_sources(unit, linked):
        archive = archives.get(source.get("archive_id"), {})
        materials = {item.get("id"): item for item in archive.get("materials") or []}
        documents = archive.get("_documents") or {}
        for material_id in source.get("material_ids") or []:
            if material_id not in materials:
                continue
            result[material_id] = {
                "material": materials[material_id], "document": documents.get(material_id, {}),
                "source_unit_id": source.get("id", ""), "source_name": source.get("title", ""),
            }
    return result


def refinement_evidence(
    base: dict,
    material_ids: list[str],
    accessible: dict[str, dict],
) -> list[dict]:
    """Return evidence constrained to the teacher-confirmed outline boundary."""
    base_nodes = [item for item in base.get("nodes") or [] if item.get("id")]
    if not material_ids:
        return []
    evidence: list[dict] = []
    for material_id in material_ids:
        entry = accessible[material_id]
        material = entry["material"]
        document = entry["document"]
        sections = list(document.get("sections") or [])
        if not sections:
            sections = [{"id": "raw", "title": material.get("name", "补充资料"), "preview": document.get("raw_text", "")[:1000]}]
        section_indexes = {str(item.get("id") or index): index for index, item in enumerate(sections)}
        outline = _display_textbook_outline(document)
        outline_indexes = {str(item.get("id")): index for index, item in enumerate(outline) if item.get("id")}
        selected_anchors: list[tuple[int, dict, dict]] = []
        for node in base_nodes:
            for source in node.get("evidence") or []:
                if source.get("material_id") != material_id:
                    continue
                match = re.fullmatch(r"section:(.+)", str(source.get("locator") or ""))
                if match and match.group(1) in outline_indexes:
                    selected_anchors.append((outline_indexes[match.group(1)], node, outline[outline_indexes[match.group(1)]]))
        allowed_by_section: dict[int, set[str]] = {}
        if selected_anchors:
            selected_outline_indexes = {item[0] for item in selected_anchors}
            for outline_index, node, anchor in selected_anchors:
                anchor_level = int(anchor.get("level") or 1)
                boundary = next((
                    index for index in range(outline_index + 1, len(outline))
                    if int(outline[index].get("level") or 1) <= anchor_level
                ), len(outline))
                # A selected parent heading is structural when selected child headings
                # already define the precise scope underneath it.
                if any(
                    index in selected_outline_indexes and int(outline[index].get("level") or 1) > anchor_level
                    for index in range(outline_index + 1, boundary)
                ):
                    continue
                start = section_indexes.get(str(anchor.get("id")), 0)
                end = len(sections)
                if boundary < len(outline):
                    end = section_indexes.get(str(outline[boundary].get("id")), end)
                for section_index in range(start, max(start + 1, end)):
                    allowed_by_section.setdefault(section_index, set()).add(node["id"])
        for index, section in enumerate(sections[:160]):
            title = re.sub(r"\s+", " ", str(section.get("title") or "")).strip()
            preview = re.sub(r"\s+", " ", str(section.get("preview") or "")).strip()
            if not title or title == "文档导言":
                continue
            allowed_parent_ids = sorted(allowed_by_section.get(index, set()))
            if not selected_anchors:
                ranked = sorted(
                    (
                        (_syllabus_similarity(f"{node.get('title', '')} {node.get('description', '')}", f"{title} {preview}")[0], node["id"])
                        for node in base_nodes
                    ),
                    reverse=True,
                )
                allowed_parent_ids = [node_id for score, node_id in ranked[:2] if score >= 0.12]
            if not allowed_parent_ids:
                continue
            evidence.append({
                "id": f"{material_id}:{section.get('id') or index}",
                "title": title,
                "content": preview[:1200],
                "material_id": material_id,
                "allowed_parent_ids": allowed_parent_ids,
                "source": {
                    "source_type": "material", "material_id": material_id,
                    "source_unit_id": entry.get("source_unit_id", ""), "document_id": material.get("document_id"),
                    "source_hash": material.get("sha256"), "locator": f"section:{section.get('id') or index}",
                    "quote": (preview or title)[:1200], "label": material.get("name", "补充资料"),
                },
            })
    return evidence


def build_refined_outline(
    base: dict,
    material_ids: list[str],
    teacher_instruction: str,
    accessible: dict[str, dict],
    model_nodes: list[dict] | None = None,
) -> dict:
    missing = [material_id for material_id in material_ids if material_id not in accessible]
    if missing:
        raise KeyError("部分细化资料不属于当前单元或关联范围")
    scoped_evidence = refinement_evidence(base, material_ids, accessible)
    evidence_by_id = {item["id"]: item for item in scoped_evidence}
    free_instruction_mode = not material_ids and bool((teacher_instruction or "").strip())
    additions: list[dict] = []
    updates: dict[str, dict] = {}
    base_node_ids = {node.get("id") for node in base.get("nodes") or []}
    existing_titles = {_normalize_text(node.get("title", "")) for node in base.get("nodes") or []}
    allow_additions = bool(re.search(r"新增|增加|补充|拆分|扩展|子知识点|下级知识点", teacher_instruction))
    if model_nodes:
        for item in model_nodes[:8]:
            if not isinstance(item, dict):
                continue
            operation = str(item.get("operation") or "add")
            target_id = str(item.get("node_id") or item.get("parent_node_id") or "")
            if target_id not in base_node_ids:
                continue
            matched = [
                evidence_by_id[eid] for eid in item.get("evidence_ids") or []
                if eid in evidence_by_id and target_id in evidence_by_id[eid]["allowed_parent_ids"]
            ]
            evidence = [item["source"] for item in matched]
            if not evidence and not free_instruction_mode:
                continue
            if operation == "update":
                description = str(item.get("description") or "").strip()[:2000]
                if description:
                    updates[target_id] = {"description": description, "evidence": evidence}
                continue
            if not allow_additions or not str(item.get("title") or "").strip():
                continue
            title = str(item["title"]).strip()[:240]
            if _normalize_text(title) in existing_titles:
                continue
            try:
                level = max(1, min(3, int(item.get("level") or 2)))
            except (TypeError, ValueError):
                level = 2
            additions.append({
                "id": str(uuid4()), "parent_id": target_id,
                "level": max(2, level), "title": title,
                "description": str(item.get("description") or "")[:2000],
                "is_key_point": bool(item.get("is_key_point")), "is_difficult_point": bool(item.get("is_difficult_point")),
                "teacher_note": teacher_instruction, "evidence": evidence,
            })
            existing_titles.add(_normalize_text(title))
    if allow_additions and not additions and not updates:
        additions_per_parent: Counter[str] = Counter()
        base_node_map = {str(node.get("id")): node for node in base.get("nodes") or []}
        for item in scoped_evidence:
            title = item["title"]
            if _normalize_text(title) in existing_titles:
                continue
            parent_id = item["allowed_parent_ids"][0]
            parent_title = _normalize_text(base_node_map.get(parent_id, {}).get("title", ""))
            normalized_title = _normalize_text(title)
            if normalized_title and parent_title and (normalized_title in parent_title or parent_title in normalized_title):
                continue
            if additions_per_parent[parent_id] >= 2:
                continue
            additions.append({
                "id": str(uuid4()), "parent_id": parent_id, "level": 2, "title": title[:240],
                "description": item["content"][:2000], "is_key_point": "重点" in teacher_instruction,
                "is_difficult_point": "难点" in teacher_instruction, "teacher_note": teacher_instruction,
                "evidence": [item["source"]],
            })
            additions_per_parent[parent_id] += 1
            existing_titles.add(normalized_title)
            if len(additions) >= 6:
                break
    refined_nodes = []
    for node in base.get("nodes") or []:
        update = updates.get(str(node.get("id")))
        refined_nodes.append({
            **node,
            **({"description": update["description"], "evidence": [*(node.get("evidence") or []), *update["evidence"]], "teacher_note": teacher_instruction} if update else {}),
        })
    return next_outline_version(base, {
        "nodes": [*refined_nodes, *additions], "teacher_instruction": teacher_instruction,
        "source_material_ids": list(dict.fromkeys([*(base.get("source_material_ids") or []), *material_ids])),
        "change_summary": (
            f"按提示词优化：完善 {len(updates)} 个知识点、新增 {len(additions)} 个下级知识点"
            if free_instruction_mode else (
                f"基于 {len(material_ids)} 份资料，在已选范围内完善 {len(updates)} 个知识点、新增 {len(additions)} 个下级知识点"
                if updates or additions else f"已分析 {len(material_ids)} 份资料，未发现属于当前知识范围的可细化内容"
            )
        ),
    })


def restructure_outline(
    base: dict,
    teacher_instruction: str,
    model_nodes: list[dict] | None = None,
) -> dict:
    """AI 优化的完整重构: 模型返回重构后的 nodes 数组, 后端映射继承证据。

    支持合并/拆分/重排结构; 不在材料范围约束下(自由扩展模式), 只受
    teacher_instruction 与现有节点证据的继承约束。
    """
    base_nodes = base.get("nodes") or []
    by_title: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for node in base_nodes:
        by_title[_normalize_text(str(node.get("title", "")))] = node
        by_id[str(node.get("id"))] = node

    # 教师指令兜底 evidence: 模型产出新节点时, 保证 KnowledgeNode.evidence >= 1
    teacher_evidence = {
        "source_type": "teacher",
        "quote": (teacher_instruction or "AI 优化新增")[:2000],
        "label": "AI 优化",
    }

    def resolve_evidence(node: dict) -> list[dict]:
        inherited = [item for item in (node.get("evidence") or []) if item.get("quote")]
        return inherited or [dict(teacher_evidence)]

    result_nodes: list[dict] = []
    id_by_title: dict[str, str] = {}
    consumed: set[str] = set()
    for item in model_nodes or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        key = _normalize_text(title)
        if key in id_by_title:
            continue
        # 尝试继承原节点: 优先按 title 归一化匹配, 其次按原 id 匹配
        original = by_title.get(key)
        if original is None:
            rid = str(item.get("id") or "")
            original = by_id.get(rid)
        node_id = original.get("id") if original and str(original.get("id")) not in consumed else str(uuid4())
        if original:
            consumed.add(str(original.get("id")))
        description = str(item.get("description") or (original.get("description", "") if original else ""))[:2000]
        try:
            level = max(1, min(3, int(item.get("level") or (original.get("level", 1) if original else 1))))
        except (TypeError, ValueError):
            level = original.get("level", 1) if original else 1
        # parent: 模型可能给 parent_title / parent_id / parent_id null
        parent_title = str(item.get("parent_title") or (item.get("parent_id") or ""))
        parent_key = _normalize_text(parent_title)
        parent_id = id_by_title.get(parent_key)
        result_nodes.append({
            "id": node_id,
            "parent_id": parent_id if parent_id != str(node_id) else None,
            "level": level,
            "title": title[:240],
            "description": description,
            "is_key_point": bool(item.get("is_key_point") or (original.get("is_key_point", False) if original else False)),
            "is_difficult_point": bool(item.get("is_difficult_point") or (original.get("is_difficult_point", False) if original else False)),
            "teacher_note": teacher_instruction,
            "evidence": resolve_evidence(
                original if original else {"source_type": "teacher", "quote": teacher_instruction, "label": "AI 优化"}
            ),
        })
        id_by_title[key] = node_id

    # 回填 parent_id: 模型输出的 parent_id 可能是后面节点的 title/id
    building_by_title: dict[str, str] = {_normalize_text(str(n["title"])): n["id"] for n in result_nodes}
    id_by_raw = {
        str(item.get("id") or ""): node["id"]
        for item in model_nodes or []
        for node in result_nodes
        if node["title"] == str(item.get("title"))
    }
    for node in result_nodes:
        raw_parent = ""
        for item in model_nodes or []:
            if node["title"] == str(item.get("title") or ""):
                raw_parent = str(item.get("parent_id") or "")
                break
        if raw_parent:
            parent_id = building_by_title.get(_normalize_text(raw_parent))
            if parent_id is None:
                parent_id = id_by_raw.get(raw_parent)
            if parent_id is not None and parent_id != node["id"]:
                node["parent_id"] = parent_id

    # 全部节点保底: 每个节点必须有 evidence
    final_nodes: list[dict] = []
    for node in result_nodes:
        if not node.get("evidence"):
            node["evidence"] = [dict(teacher_evidence)]
        final_nodes.append(node)
    if not final_nodes:
        final_nodes = base_nodes
    return next_outline_version(base, {
        "nodes": final_nodes,
        "teacher_instruction": teacher_instruction,
        "change_summary": f"按提示词重构大纲：{len(final_nodes)} 个知识点",
    })


# ---------- M7: 教材研读图谱 (选词对话 → 图谱节点) ----------

def graph_chat_section_title(document: dict, quote: str = "") -> str:
    """按选词定位其所在的教材章节标题(用于图谱节点归属/教材树精确匹配)。"""
    sections = document.get("sections") or []
    normalized_quote = re.sub(r"\s+", "", quote or "")
    # 全量章节标题里找包含 quote 的(用 display 大纲标题)
    outline = _display_textbook_outline(document)
    for section in outline:
        title = str(section.get("title") or "")
        preview = re.sub(r"\s+", " ", str(section.get("preview") or "")).strip()
        if normalized_quote and (normalized_quote in re.sub(r"\s+", "", title) or normalized_quote in re.sub(r"\s+", "", preview)):
            return title
    for section in sections:
        preview = re.sub(r"\s+", " ", str(section.get("preview") or "")).strip()
        if normalized_quote and (normalized_quote in re.sub(r"\s+", "", str(section.get("title") or "")) or normalized_quote in re.sub(r"\s+", "", preview)):
            return str(section.get("title") or "")
    return ""


def build_graph_chat_context(document: dict, quote: str = "", max_chars: int = 6000) -> str:
    """构造讨论上下文: 匹配选词所在章节(或章目录摘要), 供 LLM 回答时引用。"""
    sections = document.get("sections") or []
    raw = document.get("raw_text") or ""
    if not sections:
        return _normalize_doc(raw[:max_chars])
    # 找到 quote 所在的 section (按内容包含)
    normalized_quote = re.sub(r"\s+", " ", quote or "").strip()
    matched = None
    for section in sections:
        preview = re.sub(r"\s+", " ", str(section.get("preview") or "")).strip()
        content = re.sub(r"\s+", " ", str(section.get("content") or "")).strip()
        if normalized_quote and (normalized_quote in preview or normalized_quote in content or normalized_quote in str(section.get("title") or "")):
            matched = section
            break
    if not matched:
        # 无匹配 → 取第一个非"文档导言"章节 + 章目录
        matched = next((s for s in sections if str(s.get("title")) != "文档导言"), None)
    outline = _display_textbook_outline(document)
    catalog = "；".join(str(item.get("title")) for item in outline[:40])
    if matched and normalized_quote:
        content = re.sub(r"\s+", " ", str(matched.get("preview") or ""))
        context = (
            f"教材《{document.get('course_name') or document.get('file_name') or '教材'}》\n"
            f"章节目录：{catalog}\n"
            f"关注的原文片段(来自 {matched.get('title')} 节)：\n{content[:2600]}\n"
            f"教师选中的文本：{normalized_quote[:1600]}\n"
            "请结合以上教材内容回答教师问题；若教材未提供，明确说明并给出通用解释。"
        )
    else:
        context = (
            f"教材《{document.get('course_name') or document.get('file_name') or '教材'}》章节目录：{catalog}\n"
            "请结合整章目录与教师问题回答；教材未提供时明确说明。"
        )
    return context[:max_chars]


def _normalize_doc(value: str) -> str:
    # 缩略到可阅读长度, 保留开篇(避免超长塞入提示词)
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:6000]


def summarize_graph_chat(chat: dict) -> dict:
    """把对话整理为"图谱节点"内容 (标题 + markdown 正文)。在 LLM 侧完成则直接存;
    这里做结构化兜底: 用结论文本 + 首轮问句生成 markdown。"""
    rounds = chat.get("rounds") or []
    question = chat.get("question") or ""
    # 用最后一条 assistant 回复作为结论; 若无, 用第一条
    conclusion = ""
    for turn in reversed(rounds):
        if turn.get("role") == "assistant" and turn.get("content"):
            conclusion = turn.get("content")
            break
    md = (
        f"## 讨论主题\n{question or '教材研读'}\n\n"
        f"### 结论摘要\n{conclusion or '_无结论文本_'}\n\n"
        "### 对话记录\n" + "\n".join(
            f"- **{'教师' if t.get('role') == 'user' else 'AI'}**: {(t.get('content') or '')[:400]}"
            for t in rounds[-10:]
        )
    )
    return {"title": question[:80] if question else "教材研读补充", "content": md}
