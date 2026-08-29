from collections.abc import Iterable


def related_designs(records: Iterable[dict], archive_id: str) -> list[dict]:
    return [record for record in records if record.get("archive_id") == archive_id]


def related_runs(records: Iterable[dict], archive_id: str, designs: Iterable[dict]) -> list[dict]:
    design_ids = {record.get("id") for record in designs}
    linked_run_ids = {record.get("run_id") for record in designs if record.get("run_id")}
    result = []
    for record in records:
        teaching_data = record.get("teaching_data", {}) or {}
        if (
            teaching_data.get("archive_id") == archive_id
            or teaching_data.get("design_id") in design_ids
            or record.get("id") in linked_run_ids
        ):
            result.append(record)
    return result


def related_compositions(records: Iterable[dict], archive_id: str) -> list[dict]:
    return [
        record for record in records
        if record.get("archive_id") == archive_id
        or str(record.get("unit_id") or "").startswith(f"{archive_id}:")
    ]


def related_layouts(records: Iterable[dict], archive_id: str) -> list[dict]:
    return [record for record in records if str(record.get("unit_id") or "").startswith(f"{archive_id}:")]


def deletion_impact(
    archive: dict,
    designs: Iterable[dict],
    runs: Iterable[dict],
    compositions: Iterable[dict],
    layouts: Iterable[dict],
) -> dict:
    archive_id = archive["id"]
    matched_designs = related_designs(designs, archive_id)
    matched_runs = related_runs(runs, archive_id, matched_designs)
    matched_compositions = related_compositions(compositions, archive_id)
    matched_layouts = related_layouts(layouts, archive_id)
    document_ids = {
        material.get("document_id")
        for material in archive.get("materials", [])
        if material.get("document_id")
    }
    document_ids.update(
        record.get("import_document_id")
        for record in matched_compositions
        if record.get("import_document_id")
    )
    document_ids.update(
        item.get("document_id")
        for record in matched_designs
        for item in record.get("exports", [])
        if item.get("document_id")
    )
    return {
        "archive_id": archive_id,
        "course_title": archive.get("course_title") or archive.get("name") or "未命名课程",
        "material_count": len(archive.get("materials", [])),
        "document_count": len(document_ids),
        "design_count": len(matched_designs),
        "composition_count": len(matched_compositions),
        "run_count": len(matched_runs),
        "layout_count": len(matched_layouts),
        "_designs": matched_designs,
        "_runs": matched_runs,
        "_compositions": matched_compositions,
        "_document_ids": document_ids,
    }


def public_deletion_impact(impact: dict) -> dict:
    return {key: value for key, value in impact.items() if not key.startswith("_")}
