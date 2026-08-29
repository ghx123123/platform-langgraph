from io import BytesIO
from copy import deepcopy

import pytest
from docx import Document

from backend.data_hub.service import (
    apply_layouts,
    block_detail,
    build_catalog,
    composition_docx,
    composition_html,
    composition_markdown,
    create_library_root,
    create_data_folder,
    create_composition,
    delete_data_folder,
    delete_data_folder_recursive,
    ensure_data_folder_path,
    filter_catalog,
    organize_imported_archive,
    organize_source_archive,
    apply_platform_to_local,
    local_source_diff,
    record_local_deletions,
    register_source_manifest,
    rename_library_root,
    rename_academic_term,
    resolve_local_folder_path,
    scan_local_source,
    sync_folder_to_local,
    sync_uploads_to_local,
    transfer_local_materials,
    update_block_layout,
    update_composition,
    update_data_folder,
    unit_id,
)
from backend.data_hub.storage import delete_layouts_for_archive, list_layouts, load_layout, save_layout
from backend.course_archives.models import ArchiveManifestItem
from backend.course_archives.service import extract_course_archive_materials, remove_course_archive_materials


def sample_archive() -> dict:
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "name": "工业AI资料",
        "course_title": "工业人工智能",
        "academic_term": "2026-2027-1",
        "course_code": "AI301",
        "created_at": "2026-08-11T00:00:00Z",
        "updated_at": "2026-08-11T01:00:00Z",
        "materials": [{
            "id": "22222222-2222-4222-8222-222222222222", "path": "第10章/教材.txt",
            "name": "教材.txt", "extension": ".txt", "size": 100, "category": "textbook",
            "chapter": "第10章", "parse_status": "parsed", "document_id": "33333333-3333-4333-8333-333333333333",
            "preview_available": False, "character_count": 30, "excerpt": "深度学习与大语言模型",
        }],
        "chapters": [{"key": "第10章", "label": "第10章", "material_ids": ["22222222-2222-4222-8222-222222222222"], "material_count": 1}],
        "_documents": {"22222222-2222-4222-8222-222222222222": {"raw_text": "深度学习与大语言模型完整正文", "sections": []}},
    }


def sample_design() -> dict:
    return {
        "id": "44444444-4444-4444-8444-444444444444", "archive_id": sample_archive()["id"],
        "title": "工业人工智能 · 第10章", "chapter": "第10章", "run_id": "55555555-5555-4555-8555-555555555555",
        "version": 2, "updated_at": "2026-08-11T02:00:00Z",
        "content": {
            "objectives": ["解释大语言模型"], "key_points": ["Transformer"], "difficult_points": ["注意力机制"],
            "methods": ["案例分析"], "tools": ["教材"], "teaching_process": "问题导入与模型比较",
            "assessment": "完成模型选型", "ideological_elements": ["科技自立自强"],
        },
    }


def sample_run() -> dict:
    return {
        "id": "55555555-5555-4555-8555-555555555555", "objective": "工业AI第10章",
        "updated_at": "2026-08-11T03:00:00Z",
        "teaching_data": {"messages": [{
            "id": "q1", "agent_name": "基础型学生", "agent_type": "student", "phase": "student_question",
            "iteration": 1, "content": "为什么注意力机制可以并行计算？",
        }]},
    }


def test_catalog_connects_material_design_question_and_ideology() -> None:
    archive = sample_archive()
    catalog = build_catalog([archive], [sample_design()], [sample_run()])
    kinds = {item["kind"] for item in catalog["blocks"]}
    assert {"original", "extracted", "teaching_design", "student_question", "ideological_element"} <= kinds
    assert catalog["stats"]["terms"] == 1
    assert catalog["units"][0]["generated_count"] == 1
    extracted = next(item for item in catalog["blocks"] if item["kind"] == "extracted")
    assert "完整正文" in block_detail(extracted["id"], catalog, [archive])["content"]
    searched = filter_catalog(catalog, query="并行计算")
    assert searched["blocks"][0]["kind"] == "student_question"
    assert searched["units"][0]["chapter"] == "全课程"


def test_catalog_counts_same_named_archives_as_separate_course_roots() -> None:
    first = sample_archive()
    second = deepcopy(first)
    second["id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    catalog = build_catalog([first, second], [], [])

    assert catalog["stats"]["courses"] == 2
    assert {item["archive_id"] for item in catalog["units"]} == {first["id"], second["id"]}


def test_library_roots_are_independent_of_term_and_course_hierarchy(tmp_path) -> None:
    existing = sample_archive()
    created = create_library_root([existing], "  教学竞赛资料  ", tmp_path / "documents")

    assert created["name"] == "教学竞赛资料"
    assert created["course_title"] == "教学竞赛资料"
    assert created["academic_term"] == ""
    assert created["materials"] == []
    assert build_catalog([existing, created], [], [])["stats"]["courses"] == 2

    renamed = rename_library_root([existing, created], created["id"], "比赛支撑材料")
    assert renamed["name"] == "比赛支撑材料"
    assert renamed["course_title"] == "教学竞赛资料"
    assert renamed["academic_term"] == ""
    assert build_catalog([renamed], [], [])["units"][0]["archive_name"] == "比赛支撑材料"


def test_library_root_rejects_duplicate_sibling_names(tmp_path) -> None:
    existing = sample_archive()
    with pytest.raises(FileExistsError, match="同名文件夹"):
        create_library_root([existing], "工业AI资料", tmp_path / "documents")
    with pytest.raises(FileExistsError, match="同名文件夹"):
        rename_library_root([existing, {**existing, "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "name": "其他资料"}], "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "工业ai资料")


def test_adding_source_does_not_replace_library_root_name(tmp_path) -> None:
    existing = sample_archive()
    record, _, _, _ = register_source_manifest(
        existing,
        "新导入文件夹",
        "upload",
        [ArchiveManifestItem(path="讲义.pdf", size=20)],
        {"archive_name": "新导入文件夹", "course_title": existing["course_title"]},
        tmp_path / "documents",
    )
    assert record["name"] == existing["name"]


def test_academic_term_directory_rename_updates_all_matching_courses() -> None:
    first = sample_archive()
    first["academic_term"] = ""
    second = deepcopy(first)
    second["id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    third = deepcopy(first)
    third["id"] = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    third["academic_term"] = "2025-2026-2"

    updated = rename_academic_term([first, second, third], "未设置学期", "2026-2027-1")

    assert len(updated) == 2
    assert {item["id"] for item in updated} == {first["id"], second["id"]}
    assert {item["academic_term"] for item in updated} == {"2026-2027-1"}
    assert third["academic_term"] == "2025-2026-2"


def test_saved_composition_blocks_return_to_global_catalog() -> None:
    composition = create_composition({
        "title": "课程思政素材", "archive_id": sample_archive()["id"],
        "unit_id": build_catalog([sample_archive()], [], [])["units"][0]["id"],
        "blocks": [{"id": "i1", "kind": "ideological_element", "title": "科技报国", "content": "科技自立自强", "source_name": "教师", "locator": "draft"}],
    })
    catalog = build_catalog([sample_archive()], [], [], [composition])
    item = next(block for block in catalog["blocks"] if block["kind"] == "ideological_element")
    assert item["content"] == "科技自立自强"


def test_composition_is_editable_and_exports_three_formats() -> None:
    record = create_composition({
        "title": "第10章教学支撑包", "archive_id": sample_archive()["id"], "unit_id": "unit-10",
        "blocks": [{"id": "b1", "kind": "student_question", "title": "学生问题", "content": "为什么可以并行？", "source_name": "第1轮", "locator": "run:q1"}],
    })
    updated = update_composition(record, {**{key: record[key] for key in ("title", "archive_id", "unit_id", "blocks")}, "title": "第10章可编辑成果"})
    assert updated["version"] == 2
    assert "学生问题" in composition_markdown(updated)
    assert "学生问题" in composition_html(updated)
    doc = Document(BytesIO(composition_docx(updated)))
    assert any("第10章可编辑成果" in paragraph.text for paragraph in doc.paragraphs)


def test_local_source_rescan_indexes_only_then_extracts_selected_file(tmp_path) -> None:
    root = tmp_path / "course"
    root.mkdir()
    ignored_environment = root / ".venv"
    ignored_environment.mkdir()
    (ignored_environment / "ignored.txt").write_text("不应进入课程索引", encoding="utf-8")
    source = root / "第1章.txt"
    source.write_text("第一章课程材料，包含足够长度的正文内容。", encoding="utf-8")
    store = tmp_path / "documents"
    first, source_record, changes, removed_documents = scan_local_source(str(root), None, {"academic_term": "2026-1", "course_title": "测试课程"}, store)
    assert changes["added"] == 1
    assert first["total_files"] == 1
    assert first["parsed_files"] == 0
    assert first["materials"][0]["parse_status"] == "metadata_only"
    assert first["materials"][0]["document_id"] is None
    assert first["_documents"] == {}
    assert source_record["kind"] == "local"
    assert source_record["file_count"] == 1
    assert removed_documents == []
    source.write_text("第一章课程材料已经更新，包含新的教学内容和案例。", encoding="utf-8")
    second, refreshed_source, changes, replaced_documents = scan_local_source(
        str(root), first, {"academic_term": "2026-1", "course_title": "测试课程"}, store,
        source_record["id"], source_record["name"],
    )
    assert second["id"] == first["id"]
    assert changes["changed"] == 1
    assert second["parsed_files"] == 0
    assert second["materials"][0]["parse_status"] == "metadata_only"
    assert second["materials"][0]["document_id"] is None
    assert second["_documents"] == {}
    assert refreshed_source["id"] == source_record["id"]
    assert replaced_documents == []

    material_id = second["materials"][0]["id"]
    extracted = extract_course_archive_materials(second, [material_id], store)
    assert extracted["materials"][0]["document_id"]
    assert extracted["materials"][0]["parse_status"] == "parsed"
    assert material_id in extracted["_documents"]


def test_multiple_local_source_folders_merge_without_overwriting(tmp_path) -> None:
    first_root = tmp_path / "教材"
    second_root = tmp_path / "课件"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / "第一章.txt").write_text("教材内容", encoding="utf-8")
    (second_root / "第一章.txt").write_text("课件内容", encoding="utf-8")
    store = tmp_path / "documents"

    archive, first_source, _, _ = scan_local_source(
        str(first_root), None, {"academic_term": "2026-1", "course_title": "测试课程"}, store,
    )
    archive, second_source, changes, _ = scan_local_source(
        str(second_root), archive, {}, store,
    )

    assert first_source["id"] != second_source["id"]
    assert {item["name"] for item in archive["source_folders"]} == {"教材", "课件"}
    assert {item["path"] for item in archive["materials"]} == {"教材/第一章.txt", "课件/第一章.txt"}
    assert changes["added"] == 1


def test_browser_file_selection_is_placed_directly_in_current_folder(tmp_path) -> None:
    layout, parent = create_data_folder({"unit_id": unit_id(sample_archive()["id"], None), "folders": [], "placements": {}, "titles": {}, "updated_at": ""}, "当前目录")
    archive, source, _, _ = register_source_manifest(
        sample_archive(),
        "单文件资料",
        "upload",
        [ArchiveManifestItem(path="教学大纲.txt", size=24, last_modified=123)],
        {"academic_term": "2026-1", "course_title": "测试课程"},
        tmp_path / "documents",
        selection_kind="files",
        mount_parent_id=parent["id"],
    )
    assert source["selection_kind"] == "files"
    assert archive["source_folders"][0]["selection_kind"] == "files"

    catalog = build_catalog([archive], [], [])
    layouts, result = organize_source_archive(catalog, [layout], archive["id"], source)
    roots = [folder for layout in layouts for folder in layout["folders"] if folder.get("source_folder_id") == source["id"]]
    assert result["block_count"] == 1
    assert roots == []
    block = next(item for item in catalog["blocks"] if item["kind"] == "original" and item.get("source_folder_id") == source["id"])
    assert layouts[0]["placements"][block["id"]] == parent["id"]


def test_browser_folder_source_is_mounted_below_current_folder(tmp_path) -> None:
    archive_id = sample_archive()["id"]
    layout, parent = create_data_folder({"unit_id": unit_id(archive_id, None), "folders": [], "placements": {}, "titles": {}, "updated_at": ""}, "当前目录")
    archive, source, _, _ = register_source_manifest(
        sample_archive(),
        "新资料",
        "upload",
        [ArchiveManifestItem(path="讲义/第一讲.txt", size=24)],
        {},
        tmp_path / "documents",
        selection_kind="folder",
        mount_parent_id=parent["id"],
    )

    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [layout], archive["id"], source)
    source_root = next(item for item in layouts[0]["folders"] if item.get("source_folder_id") == source["id"])
    assert source["mount_parent_id"] == parent["id"]
    assert source_root["parent_id"] == parent["id"]
    assert next(item for item in layouts[0]["folders"] if item["name"] == "讲义")["parent_id"] == source_root["id"]


def test_refreshing_outer_source_preserves_nested_source_mount(tmp_path) -> None:
    archive, outer, _, _ = register_source_manifest(
        sample_archive(), "外层来源", "upload",
        [ArchiveManifestItem(path="外层文件.txt", size=10)], {}, tmp_path / "documents",
    )
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], outer)
    outer_root = next(item for item in layouts[0]["folders"] if item.get("source_folder_id") == outer["id"])
    archive, inner, _, _ = register_source_manifest(
        archive, "内层来源", "upload",
        [ArchiveManifestItem(path="内层文件.txt", size=8)], {}, tmp_path / "documents",
        mount_parent_id=outer_root["id"],
    )
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), layouts, archive["id"], inner)
    inner_root = next(item for item in layouts[0]["folders"] if item.get("source_folder_id") == inner["id"])

    refreshed_layouts, _ = organize_source_archive(build_catalog([archive], [], []), layouts, archive["id"], outer)

    refreshed_ids = {item["id"] for item in refreshed_layouts[0]["folders"]}
    assert outer_root["id"] in refreshed_ids
    assert inner_root["id"] in refreshed_ids
    assert next(item for item in refreshed_layouts[0]["folders"] if item["id"] == inner_root["id"])["parent_id"] == outer_root["id"]


def test_local_materials_can_be_copied_or_moved_inside_same_source(tmp_path) -> None:
    root = tmp_path / "本机资料"
    root.mkdir()
    (root / "复制.txt").write_text("复制内容", encoding="utf-8")
    (root / "移动.txt").write_text("移动内容", encoding="utf-8")
    archive, source, _, _ = scan_local_source(str(root), None, {"course_title": "本机资料"}, tmp_path / "documents")
    catalog = build_catalog([archive], [], [])
    layouts, _ = organize_source_archive(catalog, [], archive["id"], source)
    layout = layouts[0]
    source_root = next(item for item in layout["folders"] if item.get("source_folder_id") == source["id"])
    layout, destination = create_data_folder(layout, "目标目录", source_root["id"])
    blocks = {item["title"]: item for item in catalog["blocks"] if item["kind"] == "original"}

    _, copied = transfer_local_materials(archive, layout, [blocks["复制.txt"]["id"]], destination["id"], "copy")
    with pytest.raises(FileExistsError, match="同名文件"):
        transfer_local_materials(archive, layout, [blocks["复制.txt"]["id"]], destination["id"], "copy")
    _, moved = transfer_local_materials(archive, layout, [blocks["移动.txt"]["id"]], destination["id"], "move")

    assert copied == moved == 1
    assert (root / "复制.txt").is_file()
    assert (root / "目标目录" / "复制.txt").is_file()
    assert not (root / "移动.txt").exists()
    assert (root / "目标目录" / "移动.txt").is_file()
    refreshed, _, changes, _ = scan_local_source(
        str(root), archive, {}, tmp_path / "documents", source["id"], source["name"],
    )
    moved_material = next(item for item in refreshed["materials"] if item["name"] == "移动.txt")
    assert moved_material["id"] == blocks["移动.txt"]["id"].split(":")[2]
    assert moved_material["source_relative_path"] == "目标目录/移动.txt"
    assert changes["changed"] >= 1


def test_created_platform_folder_can_sync_to_local_source(tmp_path) -> None:
    root = tmp_path / "本机资料"
    root.mkdir()
    archive, source, _, _ = scan_local_source(str(root), None, {"course_title": "同步测试"}, tmp_path / "documents")
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], source)
    layout = layouts[0]
    source_root = next(item for item in layout["folders"] if item.get("source_folder_id") == source["id"])
    layout, created = create_data_folder(layout, "新建教案", source_root["id"])

    resolved_source, created_count = sync_folder_to_local(archive, layout, created["id"])
    _, repeated_count = sync_folder_to_local(archive, layout, created["id"])

    assert resolved_source["id"] == source["id"]
    assert created_count == 1
    assert repeated_count == 0
    assert (root / "新建教案").is_dir()


def test_browser_uploads_sync_nested_files_and_empty_directories(tmp_path) -> None:
    root = tmp_path / "本机资料"
    root.mkdir()
    archive, source, _, _ = scan_local_source(str(root), None, {"course_title": "同步测试"}, tmp_path / "documents")
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], source)
    layout = layouts[0]
    source_root = next(item for item in layout["folders"] if item.get("source_folder_id") == source["id"])
    layout, destination = create_data_folder(layout, "收件箱", source_root["id"])

    resolved_source, file_count, directory_count = sync_uploads_to_local(
        archive,
        layout,
        destination["id"],
        "课程资料",
        ["空目录", "章节/完全空"],
        [("说明.txt", b"overview"), ("章节/第一讲.txt", "第一讲".encode("utf-8"))],
    )

    assert resolved_source["id"] == source["id"]
    assert file_count == 2
    assert directory_count >= 4
    assert (root / "收件箱" / "课程资料" / "说明.txt").read_bytes() == b"overview"
    assert (root / "收件箱" / "课程资料" / "章节" / "第一讲.txt").read_text(encoding="utf-8") == "第一讲"
    assert (root / "收件箱" / "课程资料" / "空目录").is_dir()
    assert (root / "收件箱" / "课程资料" / "章节" / "完全空").is_dir()
    with pytest.raises(FileExistsError, match="同名文件"):
        sync_uploads_to_local(archive, layout, destination["id"], "课程资料", [], [("说明.txt", b"duplicate")])
    with pytest.raises(ValueError, match="同步目录之外"):
        sync_uploads_to_local(archive, layout, destination["id"], "", [], [("../越界.txt", b"blocked")])
    assert not (root.parent / "越界.txt").exists()


def test_local_path_resolution_crosses_nested_browser_source_root(tmp_path) -> None:
    root = tmp_path / "本机资料"
    root.mkdir()
    archive, source, _, _ = scan_local_source(str(root), None, {"course_title": "同步测试"}, tmp_path / "documents")
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], source)
    layout = layouts[0]
    source_root = next(item for item in layout["folders"] if item.get("source_folder_id") == source["id"])
    layout, browser_root = create_data_folder(layout, "浏览器上传", source_root["id"])
    browser_folder = next(item for item in layout["folders"] if item["id"] == browser_root["id"])
    browser_folder.update({"source_folder_id": "browser-source", "source_kind": "upload"})
    layout, child = create_data_folder(layout, "空目录", browser_root["id"])

    resolved_source, target, relative = resolve_local_folder_path(archive, layout, child["id"])

    assert resolved_source["id"] == source["id"]
    assert target == root / "浏览器上传" / "空目录"
    assert relative == "浏览器上传/空目录"


def test_local_source_diff_reports_both_sides_without_changing_files(tmp_path) -> None:
    root = tmp_path / "本机资料"
    root.mkdir()
    first = root / "平台文件.txt"
    first.write_text("平台版本", encoding="utf-8")
    archive, source, _, _ = scan_local_source(str(root), None, {"course_title": "双向同步"}, tmp_path / "documents")
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], source)
    layout = layouts[0]
    material = archive["materials"][0]
    archive = record_local_deletions(archive, {material["id"]})
    archive, _ = remove_course_archive_materials(archive, {material["id"]})
    (root / "本地新增.txt").write_text("新增", encoding="utf-8")
    (root / "本地空目录").mkdir()

    diff = local_source_diff(archive, layout, source["id"], tmp_path / "documents")

    statuses = {(item["path"], item["status"]) for item in diff["items"]}
    assert ("平台文件.txt", "platform_deleted") in statuses
    assert ("本地新增.txt", "local_added") in statuses
    assert ("本地空目录", "local_directory_added") in statuses
    assert first.is_file()
    assert diff["platform_changes"] == 1
    assert diff["local_changes"] == 2


def test_platform_to_local_applies_safe_deletions_and_keeps_nonempty_folders(tmp_path) -> None:
    root = tmp_path / "本机资料"
    nested = root / "待删目录"
    nested.mkdir(parents=True)
    tracked = nested / "已知文件.txt"
    tracked.write_text("平台已知", encoding="utf-8")
    archive, source, _, _ = scan_local_source(str(root), None, {"course_title": "双向同步"}, tmp_path / "documents")
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], source)
    layout = layouts[0]
    material = archive["materials"][0]
    archive = record_local_deletions(archive, {material["id"]}, [f"{source['id']}\u0000待删目录"])
    archive, _ = remove_course_archive_materials(archive, {material["id"]})
    untracked = nested / "后来新增.txt"
    untracked.write_text("不得误删", encoding="utf-8")

    applied, skipped = apply_platform_to_local(archive, layout, source["id"], tmp_path / "documents")

    assert not tracked.exists()
    assert untracked.read_text(encoding="utf-8") == "不得误删"
    assert nested.is_dir()
    assert applied == 1
    assert skipped >= 1
    assert not archive["_local_sync_deletions"]


def test_platform_to_local_removes_untracked_local_file(tmp_path) -> None:
    root = tmp_path / "本机资料"
    root.mkdir()
    archive, source, _, _ = scan_local_source(str(root), None, {"course_title": "双向同步"}, tmp_path / "documents")
    layouts, _ = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], source)
    local_only = root / "本地新增.txt"
    local_only.write_text("仅本地", encoding="utf-8")

    applied, skipped = apply_platform_to_local(archive, layouts[0], source["id"], tmp_path / "documents")

    assert applied == 1
    assert skipped == 0
    assert not local_only.exists()


def test_source_name_rejects_path_separators(tmp_path) -> None:
    with pytest.raises(ValueError, match="斜杠"):
        register_source_manifest(
            sample_archive(), "教材/新版", "upload", [], {}, tmp_path / "documents",
        )


def test_local_source_preserves_empty_directories(tmp_path) -> None:
    root = tmp_path / "262701"
    (root / "python" / "嵌套空目录").mkdir(parents=True)

    archive, source, changes, _ = scan_local_source(
        str(root), None, {"course_title": "空目录测试"}, tmp_path / "documents",
    )

    assert archive["total_files"] == 0
    assert changes["added"] == 0
    assert source["file_count"] == 0
    assert source["directory_count"] == 2
    assert source["directory_paths"] == ["python", "python/嵌套空目录"]

    catalog = build_catalog([archive], [], [])
    layouts, result = organize_source_archive(catalog, [], archive["id"], source)
    folders = layouts[0]["folders"]
    root_folder = next(item for item in folders if item.get("source_folder_id") == source["id"])
    python_folder = next(item for item in folders if item["name"] == "python")
    nested_folder = next(item for item in folders if item["name"] == "嵌套空目录")
    assert root_folder["name"] == "262701"
    assert python_folder["parent_id"] == root_folder["id"]
    assert nested_folder["parent_id"] == python_folder["id"]
    assert result["folder_count"] == 3
    assert result["block_count"] == 0


def test_browser_source_can_register_a_completely_empty_folder(tmp_path) -> None:
    archive, source, changes, _ = register_source_manifest(
        None,
        "完全空目录",
        "upload",
        [],
        {"course_title": "空目录测试"},
        tmp_path / "documents",
        selection_kind="folder",
        directory_paths=[],
    )

    assert archive["total_files"] == 0
    assert source["file_count"] == 0
    assert source["directory_count"] == 0
    assert changes["added"] == 0
    layouts, result = organize_source_archive(build_catalog([archive], [], []), [], archive["id"], source)
    roots = [folder for folder in layouts[0]["folders"] if folder.get("source_folder_id") == source["id"]]
    assert [folder["name"] for folder in roots] == ["完全空目录"]
    assert result["folder_count"] == 1


def test_adding_empty_source_does_not_rebuild_existing_materials(tmp_path) -> None:
    existing = sample_archive()
    existing["materials"][0]["path"] = "."
    existing["total_files"] = len(existing["materials"])
    original_material = deepcopy(existing["materials"][0])

    archive, source, _, _ = register_source_manifest(
        existing,
        "空目录来源",
        "local",
        [],
        {},
        tmp_path / "documents",
        root_path=str(tmp_path / "empty"),
        directory_paths=["python"],
    )

    assert archive["materials"] == [original_material]
    assert archive["total_files"] == existing["total_files"]
    assert source["directory_paths"] == ["python"]


def test_catalog_combines_chaptered_and_uncategorized_materials_in_course_directory() -> None:
    archive = sample_archive()
    archive["materials"][0]["chapter"] = "第10章"
    archive["materials"].append({
        "id": "44444444-4444-4444-8444-444444444444",
        "path": "课程说明.txt",
        "name": "课程说明.txt",
        "extension": ".txt",
        "size": 20,
        "category": "other",
        "chapter": None,
        "parse_status": "metadata_only",
        "document_id": None,
        "preview_available": False,
        "character_count": 0,
        "excerpt": "",
    })

    summary = build_catalog([archive], [], [], include_blocks=False)
    course_unit_id = unit_id(archive["id"], None)
    assert summary["blocks"] == []
    assert summary["stats"]["units"] == 1
    assert len(summary["units"]) == 1
    assert summary["units"][0]["id"] == course_unit_id
    assert summary["units"][0]["material_count"] == 2

    detail = build_catalog([archive], [], [], target_unit_id=course_unit_id)
    original_blocks = [item for item in detail["blocks"] if item["kind"] == "original"]
    assert {item["title"] for item in original_blocks} == {"教材.txt", "课程说明.txt"}
    assert {item["unit_id"] for item in original_blocks} == {course_unit_id}


def test_data_hub_folder_layout_persists_and_applies_to_blocks(tmp_path) -> None:
    catalog = build_catalog([sample_archive()], [], [])
    unit = catalog["units"][0]
    block = next(item for item in catalog["blocks"] if item["kind"] == "original")
    layout = {"unit_id": unit["id"], "folders": [], "placements": {}, "titles": {}, "updated_at": ""}
    layout, root = create_data_folder(layout, "课堂案例")
    layout, child = create_data_folder(layout, "第一讲", parent_id=root["id"])
    layout = update_block_layout(layout, block["id"], title="导入教材.txt", move=True, folder_id=child["id"])
    save_layout(tmp_path, layout)

    restored = load_layout(tmp_path, unit["id"])
    assert list_layouts(tmp_path)[0]["unit_id"] == unit["id"]
    arranged = apply_layouts(catalog, [restored])
    arranged_block = next(item for item in arranged["blocks"] if item["id"] == block["id"])
    assert arranged_block["title"] == "导入教材.txt"
    assert arranged_block["folder_id"] == child["id"]
    assert {item["name"] for item in arranged["folders"]} == {"课堂案例", "第一讲"}


def test_layout_flattens_original_root_and_merges_same_named_folders(tmp_path) -> None:
    layout = {"unit_id": "unit-1", "folders": [], "placements": {}, "titles": {}, "updated_at": ""}
    layout, main_folder = create_data_folder(layout, "262701")
    layout, legacy_folder = create_data_folder(layout, "262701", system_parent="original")
    layout, child = create_data_folder(layout, "课件", parent_id=legacy_folder["id"])
    layout = update_block_layout(layout, "block-main", move=True, folder_id=main_folder["id"])
    layout = update_block_layout(layout, "block-legacy", move=True, folder_id=legacy_folder["id"])
    layout = update_block_layout(layout, "block-child", move=True, folder_id=child["id"])

    save_layout(tmp_path, layout)
    restored = load_layout(tmp_path, "unit-1")

    roots = [item for item in restored["folders"] if item.get("parent_id") is None]
    assert [(item["name"], item.get("system_parent")) for item in roots] == [("262701", None)]
    assert next(item for item in restored["folders"] if item["name"] == "课件")["parent_id"] == roots[0]["id"]
    assert restored["placements"] == {
        "block-main": roots[0]["id"],
        "block-legacy": roots[0]["id"],
        "block-child": child["id"],
    }


def test_data_hub_folder_rejects_duplicates_cycles_and_non_empty_delete() -> None:
    layout = {"unit_id": "unit-1", "folders": [], "placements": {}, "titles": {}, "updated_at": ""}
    layout, root = create_data_folder(layout, "课程资源", system_parent="original")
    with pytest.raises(FileExistsError):
        create_data_folder(layout, "课程资源", system_parent="original")
    layout, child = create_data_folder(layout, "案例", parent_id=root["id"])
    with pytest.raises(ValueError, match="子文件夹"):
        update_data_folder(layout, root["id"], move=True, parent_id=child["id"])
    layout = update_block_layout(layout, "block-1", move=True, folder_id=child["id"])
    with pytest.raises(RuntimeError, match="仍有资料"):
        delete_data_folder(layout, child["id"])
    layout = update_block_layout(layout, "block-1", move=True, folder_id=None)
    layout = delete_data_folder(layout, child["id"])
    layout = delete_data_folder(layout, root["id"])
    assert layout["folders"] == []


def test_imported_archive_is_grouped_under_named_folders() -> None:
    catalog = build_catalog([sample_archive()], [], [])
    layouts, summary = organize_imported_archive(catalog, [], sample_archive()["id"], "第10章教材导入")
    arranged = apply_layouts(catalog, layouts)
    assert summary == {
        "archive_id": sample_archive()["id"], "unit_count": 1, "folder_count": 1, "block_count": 1,
    }
    assert {item["name"] for item in arranged["folders"]} == {"第10章教材导入"}
    assert next(item for item in arranged["blocks"] if item["kind"] == "original").get("folder_id")


def test_archive_layouts_can_be_removed_together(tmp_path) -> None:
    archive_id = "11111111-1111-4111-8111-111111111111"
    save_layout(tmp_path, {"unit_id": f"{archive_id}:chapter-1", "folders": [], "placements": {}, "titles": {}, "updated_at": ""})
    save_layout(tmp_path, {"unit_id": "other:chapter-1", "folders": [], "placements": {}, "titles": {}, "updated_at": ""})
    assert delete_layouts_for_archive(tmp_path, archive_id) == 1
    assert [item["unit_id"] for item in list_layouts(tmp_path)] == ["other:chapter-1"]


def test_recursive_folder_delete_returns_contained_blocks() -> None:
    layout = {"unit_id": "unit-1", "folders": [], "placements": {}, "titles": {}, "updated_at": ""}
    layout, root_id, created = ensure_data_folder_path(layout, ["教材", "案例"], system_parent="original")
    assert root_id
    assert created == 2
    block_id = "material:archive:material:original"
    layout = update_block_layout(layout, block_id, move=True, folder_id=root_id)
    top = next(item for item in layout["folders"] if item["name"] == "教材")
    cleaned, block_ids = delete_data_folder_recursive(layout, top["id"])
    assert block_ids == {block_id}
    assert cleaned["folders"] == []
    assert cleaned["placements"] == {}
