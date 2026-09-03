import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.course_archives.models import ArchiveManifestItem
from backend.course_archives.service import analyze_course_archive, extract_course_archive_materials
from backend.course_archives.storage import save_archive
from backend.material_units import router as material_unit_router
from backend.material_units.models import KnowledgeNode
from backend.material_units.service import (
    build_initial_outline, build_material_unit_file, build_refined_outline, build_scope_options,
    create_or_update_material_unit, material_unit_summary, match_syllabus_requirements,
    merge_material_units, refinement_evidence,
)
from backend.material_units.storage import delete_material_unit, delete_material_units_for_archive, list_material_units, load_material_unit, save_material_unit


def _unit_record(unit_id: str, title: str, linked_units: list[dict] | None = None) -> dict:
    return {
        "id": unit_id,
        "archive_id": "archive-a",
        "archive_name": "Python程序设计",
        "title": title,
        "material_ids": [],
        "files": [],
        "linked_units": linked_units or [],
        "linked_unit_count": len(linked_units or []),
        "source_category_counts": {},
        "material_count": 0,
        "parsed_count": 0,
        "total_characters": 0,
        "overview": "尚未加入资料",
        "key_points": [],
        "created_at": "2026-08-12T01:00:00Z",
        "updated_at": "2026-08-12T01:00:00Z",
    }


def _material_unit_client(monkeypatch, tmp_path, model=None) -> TestClient:
    settings = SimpleNamespace(
        material_unit_store_path=tmp_path / "units",
        course_archive_store_path=tmp_path / "archives",
        course_design_store_path=tmp_path / "designs",
        document_store_path=tmp_path / "documents",
    )
    monkeypatch.setattr(material_unit_router, "get_settings", lambda: settings)
    api = FastAPI()
    if model is not None:
        api.state.workflow_service = SimpleNamespace(model=model)
    api.include_router(material_unit_router.router)
    return TestClient(api)


def _analysis_file(material_id: str, name: str, category: str, archive_id: str) -> dict:
    return {
        "material_id": material_id,
        "name": name,
        "path": name,
        "category": category,
        "extension": ".docx",
        "document_id": f"doc-{material_id}",
        "preview_available": True,
        "parse_status": "parsed",
        "parse_message": "",
        "character_count": 100,
        "summary": name,
        "section_count": 2,
        "knowledge_points": [],
        "extraction_engine": "test",
        "quality_level": "high",
        "archive_id": archive_id,
    }


def _scope_fixture(monkeypatch, tmp_path, model=None):
    archive_id = "11111111-1111-4111-8111-111111111111"
    unit_id = "22222222-2222-4222-8222-222222222222"
    materials = [
        {"id": "schedule", "name": "教学进度表.xlsx", "path": "教学进度表.xlsx", "extension": ".xlsx", "category": "schedule", "parse_status": "parsed", "character_count": 100, "document_id": "doc-schedule", "sha256": "schedule-hash"},
        {"id": "syllabus", "name": "课程大纲.docx", "path": "课程大纲.docx", "extension": ".docx", "category": "syllabus", "parse_status": "parsed", "character_count": 600, "document_id": "doc-syllabus", "sha256": "syllabus-hash"},
        {"id": "book", "name": "Python教材.pdf", "path": "Python教材.pdf", "extension": ".pdf", "category": "textbook", "parse_status": "parsed", "character_count": 800, "document_id": "doc-book", "sha256": "book-hash"},
        {"id": "guide", "name": "变量实验指导书.docx", "path": "变量实验指导书.docx", "extension": ".docx", "category": "experiment", "parse_status": "parsed", "character_count": 300, "document_id": "doc-guide", "sha256": "guide-hash"},
    ]
    archive = {
        "id": archive_id,
        "name": "Python资料",
        "course_title": "Python程序设计",
        "updated_at": "2026-08-12T01:00:00Z",
        "materials": materials,
        "schedule": [
            {"id": "lesson-2", "label": "第2次课", "content": "2 第2次课 第二章 变量、数据类型与运算符", "chapter": "第2章", "source_material_id": "schedule"},
            {"id": "lesson-8", "label": "第8次课", "content": "8 第8次课 第八章 文件与异常处理", "chapter": "第8章", "source_material_id": "schedule"},
        ],
        "_documents": {
            "schedule": {"raw_text": "2 第2次课 第二章 变量、数据类型与运算符"},
            "syllabus": {"sections": [
                {"id": "goal-2", "title": "第二章课程目标", "preview": "理解变量与数据类型，掌握运算符表达式"},
                {"id": "knowledge-2", "title": "第二章知识要求", "preview": "掌握变量定义、数据类型转换和运算符"},
                {"id": "key-2", "title": "第二章教学重点", "preview": "变量、数据类型与表达式"},
                {"id": "hard-2", "title": "第二章教学难点", "preview": "数据类型转换与运算符优先级"},
                {"id": "practice-2", "title": "第二章实践要求", "preview": "上机完成变量和表达式实验"},
                {"id": "assessment-2", "title": "第二章考核要求", "preview": "考核变量与运算符的正确应用"},
                {"id": "chapter-8", "title": "第八章知识要求", "preview": "掌握文件读写和异常处理"},
                {"id": "chapter-9", "title": "第九章知识要求", "preview": "理解类、对象与继承"},
            ]},
            "book": {"sections": [
                {"id": "c2", "title": "第2章 内置对象、运算符与表达式", "level": 1, "preview": "变量和数据类型"},
                {"id": "s21", "title": "2.1 常量与变量", "level": 2, "preview": "变量定义和命名"},
                {"id": "s22", "title": "2.2 运算符与表达式", "level": 2, "preview": "运算符优先级"},
            ]},
            "guide": {"sections": [
                {"id": "g1", "title": "变量命名规范", "preview": "变量名应清晰表达数据含义"},
                {"id": "g2", "title": "类型转换边界", "preview": "字符串与数值转换需要处理非法输入"},
            ]},
        },
    }
    unit = _unit_record(unit_id, "Python程序设计资料单元")
    unit.update({
        "archive_id": archive_id,
        "archive_name": "Python程序设计",
        "material_ids": [item["id"] for item in materials],
        "files": [_analysis_file(item["id"], item["name"], item["category"], archive_id) for item in materials],
        "material_count": len(materials),
        "parsed_count": len(materials),
        "total_characters": 1800,
    })
    save_archive(tmp_path / "archives", archive)
    save_material_unit(tmp_path / "units", unit)
    return _material_unit_client(monkeypatch, tmp_path, model), unit_id


def test_material_unit_persists_extracted_analysis_snapshot(tmp_path):
    path = "课程/第3章/工业视觉.md"
    data = "# 第3章 工业视觉\n## 图像分类\n卷积神经网络用于水果分拣与缺陷检测。".encode()
    archive = analyze_course_archive(
        "工业人工智能",
        [ArchiveManifestItem(path=path, size=len(data))],
        [(path, data)],
        tmp_path / "documents",
        extract_uploads=False,
    )
    material_id = archive["materials"][0]["id"]
    archive = extract_course_archive_materials(archive, [material_id], tmp_path / "documents")

    unit = create_or_update_material_unit(archive, "第3讲 工业视觉", [material_id])
    save_material_unit(tmp_path / "units", unit)
    restored = load_material_unit(tmp_path / "units", unit["id"])

    assert restored["material_count"] == 1
    assert restored["parsed_count"] == 1
    assert restored["files"][0]["character_count"] > 0
    assert "卷积神经网络" in restored["files"][0]["summary"]
    assert restored["files"][0]["extraction_engine"]
    assert list_material_units(tmp_path / "units")[0]["id"] == unit["id"]
    assert material_unit_summary(restored)["title"] == "第3讲 工业视觉"


def test_material_unit_append_reuses_archive_document_analysis(tmp_path, monkeypatch):
    path = "课程/控制系统.md"
    data = "# 控制系统\n闭环控制、稳定性与工程案例。".encode()
    archive = analyze_course_archive(
        "自动控制",
        [ArchiveManifestItem(path=path, size=len(data))],
        [(path, data)],
        tmp_path / "documents",
        extract_uploads=False,
    )
    material_id = archive["materials"][0]["id"]
    archive = extract_course_archive_materials(archive, [material_id], tmp_path / "documents")
    first_document = archive["_documents"][material_id]
    unit = create_or_update_material_unit(archive, "控制系统基础", [material_id])

    def fail_if_parsed_again(*_args, **_kwargs):
        raise AssertionError("cached material should not be parsed again")

    monkeypatch.setattr("backend.course_archives.service._parse_uploaded", fail_if_parsed_again)
    archive = extract_course_archive_materials(archive, [material_id], tmp_path / "documents")
    updated = create_or_update_material_unit(archive, unit["title"], [material_id], unit)

    assert archive["_documents"][material_id] is first_document
    assert updated["material_ids"] == [material_id]
    assert updated["parsed_count"] == 1


def test_delete_material_units_for_archive_only_removes_matching_records(tmp_path):
    root = tmp_path / "units"
    first = {"id": "b4289093-0c9a-414d-a98e-9b6f99629979", "archive_id": "archive-a", "updated_at": "2026-08-12T01:00:00Z"}
    second = {"id": "73e578cf-54ee-44f2-9097-3116a072b9b7", "archive_id": "archive-b", "updated_at": "2026-08-12T02:00:00Z"}
    save_material_unit(root, first)
    save_material_unit(root, second)

    assert delete_material_units_for_archive(root, "archive-a") == 1
    assert [item["id"] for item in list_material_units(root)] == [second["id"]]


def test_merge_material_units_keeps_cross_archive_source_as_link():
    target = {
        "id": "target", "archive_id": "archive-a", "archive_name": "Python", "title": "教材",
        "material_ids": ["book"], "files": [{"material_id": "book", "category": "textbook", "parse_status": "parsed", "character_count": 100, "knowledge_points": ["变量"]}],
        "linked_units": [], "created_at": "2026-08-12T01:00:00Z", "updated_at": "2026-08-12T01:00:00Z",
    }
    source = {
        "id": "source", "archive_id": "archive-b", "archive_name": "202601", "title": "大纲与进度",
        "material_ids": ["schedule"], "files": [{"material_id": "schedule", "category": "schedule", "parse_status": "parsed", "character_count": 50, "knowledge_points": []}],
        "material_count": 1,
    }
    merged = merge_material_units(target, [source], "Python程序设计基础与应用")
    assert merged["title"] == "Python程序设计基础与应用"
    assert merged["linked_unit_count"] == 1
    assert merged["material_count"] == 2
    assert merged["files"][1]["source_unit_id"] == "source"
    assert merged["linked_units"][0]["title"] == "大纲与进度"


def test_scope_options_align_schedule_syllabus_and_textbook_outline():
    unit = {"id": "unit", "archive_id": "archive", "archive_name": "Python", "title": "第2章", "linked_units": [], "material_ids": ["schedule", "syllabus", "book"]}
    archive = {
        "id": "archive",
        "schedule": [{"id": "s1", "label": "第3讲", "content": "第3讲 变量与运算符", "source_material_id": "schedule"}],
        "materials": [
            {"id": "schedule", "category": "schedule"},
            {"id": "syllabus", "category": "syllabus"},
            {"id": "book", "category": "textbook"},
        ],
        "_documents": {
            "syllabus": {"raw_text": "掌握变量、数据类型与运算符\n能够编写简单程序", "sections": [
                {"title": "课程目标", "preview": "掌握变量、数据类型与运算符"},
                {"title": "能力要求", "preview": "能够编写简单程序"},
            ]},
            "book": {"sections": [
                {"id": "c2", "title": "第2章 内置对象", "level": 1, "preview": "章节导言"},
                {"id": "s21", "title": "2.1 常量与变量", "level": 2, "preview": "变量类型"},
                {"id": "s211", "title": "2.1.1 变量", "level": 4, "preview": "变量定义"},
            ]},
        },
    }
    options = build_scope_options(unit, [], {"archive": archive})
    assert options["teaching_items"][0]["title"] == "第3讲"
    assert len(options["syllabus_items"]) == 2
    assert [item["level"] for item in options["textbook_outline"]] == [1, 2, 3]
    outline = build_initial_outline(options, {
        "teaching_item_ids": [options["teaching_items"][0]["id"]],
        "syllabus_item_ids": [options["syllabus_items"][0]["id"]],
        "outline_node_ids": [item["id"] for item in options["textbook_outline"][1:]],
        "title": "变量与运算符",
    })
    assert outline["title"] == "变量与运算符"
    assert outline["session"] == "第3讲"
    assert outline["sections"] == ["2.1 常量与变量", "2.1.1 变量"]


def test_scope_options_falls_back_to_textbook_knowledge_points():
    unit = {"id": "unit", "archive_id": "archive", "archive_name": "控制", "title": "第2章", "linked_units": [], "material_ids": ["book"]}
    archive = {
        "id": "archive",
        "schedule": [],
        "materials": [{"id": "book", "category": "textbook", "document_id": "doc-book"}],
        "_documents": {"book": {
            "raw_text": "扫描教材正文",
            "sections": [],
            "knowledge_points": [
                {"title": "第2章 机电传动系统动力学", "description": "章节概述"},
                {"title": "2.1 运动方程", "description": "转矩平衡"},
                {"title": "2.1.1 多轴系统折算", "description": "惯量与转矩折算"},
            ],
        }},
    }

    options = build_scope_options(unit, [], {"archive": archive})

    assert [item["title"] for item in options["textbook_outline"]] == [
        "第2章 机电传动系统动力学", "2.1 运动方程", "2.1.1 多轴系统折算",
    ]
    assert [item["level"] for item in options["textbook_outline"]] == [1, 2, 3]


def test_scope_options_falls_back_to_numbered_raw_text_headings():
    unit = {"id": "unit", "archive_id": "archive", "archive_name": "控制", "title": "第2章", "linked_units": [], "material_ids": ["book"]}
    archive = {
        "id": "archive",
        "schedule": [],
        "materials": [{"id": "book", "category": "textbook"}],
        "_documents": {"book": {
            "raw_text": "第2章 机电传动系统动力学\n正文说明\n2.1 运动方程\n转矩平衡\n2.1.1 多轴系统折算\n详细说明",
            "sections": [],
            "knowledge_points": [],
        }},
    }

    options = build_scope_options(unit, [], {"archive": archive})

    assert [item["title"] for item in options["textbook_outline"]] == [
        "第2章 机电传动系统动力学", "2.1 运动方程", "2.1.1 多轴系统折算",
    ]


def test_textbook_file_snapshot_uses_same_clean_outline_as_scope_options():
    material = {
        "id": "book", "name": "扫描教材.pdf", "category": "textbook", "extension": ".pdf",
        "parse_status": "parsed", "character_count": 100,
    }
    document = {
        "raw_text": "第二章 机电传动控制的数学模型",
        "sections": [
            {"id": "chapter", "title": "第二章", "level": 1, "preview": ""},
            {"id": "chapter-tail", "title": "机电传动控制的", "level": 1, "preview": ""},
            {"id": "chapter-tail-2", "title": "数学模型", "level": 1, "preview": "述"},
            {"id": "section", "title": "第一节 概", "level": 2, "preview": "述 数学模型的概念。"},
            {"id": "header", "title": "机电传动控制的数学模型17", "level": 1, "preview": ""},
        ],
        "knowledge_points": [{"title": "机电传动控制的"}, {"title": "数学模型"}],
        "extraction_report": {"engine": "PyMuPDF + RapidOCR v6", "quality_level": "medium"},
    }

    snapshot = build_material_unit_file(material, document)

    assert snapshot["knowledge_points"] == ["第二章 机电传动控制的数学模型", "第一节 概述"]


def test_delete_single_material_unit(tmp_path):
    root = tmp_path / "units"
    record = {"id": "b4289093-0c9a-414d-a98e-9b6f99629979", "archive_id": "archive-a"}
    save_material_unit(root, record)
    delete_material_unit(root, record["id"])
    assert list_material_units(root) == []


def test_reference_api_rejects_direct_circular_link(monkeypatch, tmp_path):
    client = _material_unit_client(monkeypatch, tmp_path)
    first_id = "b4289093-0c9a-414d-a98e-9b6f99629979"
    second_id = "73e578cf-54ee-44f2-9097-3116a072b9b7"
    first = _unit_record(first_id, "教材", [{
        "unit_id": second_id,
        "title": "大纲与进度表",
        "archive_id": "archive-a",
        "archive_name": "Python程序设计",
        "material_count": 0,
        "files": [],
    }])
    second = _unit_record(second_id, "大纲与进度表")
    save_material_unit(tmp_path / "units", first)
    save_material_unit(tmp_path / "units", second)

    response = client.post(f"/api/material-units/{second_id}/references", json={"unit_ids": [first_id]})

    assert response.status_code == 422
    assert "循环引用" in response.json()["detail"]
    assert load_material_unit(tmp_path / "units", second_id)["linked_units"] == []


def test_reference_api_rejects_transitive_circular_link(monkeypatch, tmp_path):
    client = _material_unit_client(monkeypatch, tmp_path)
    first_id = "b4289093-0c9a-414d-a98e-9b6f99629979"
    second_id = "73e578cf-54ee-44f2-9097-3116a072b9b7"
    third_id = "06649a7e-e20d-45ca-9080-56ba3fb01c38"
    link = lambda unit_id, title: {
        "unit_id": unit_id, "title": title, "archive_id": "archive-a",
        "archive_name": "Python程序设计", "material_count": 0, "files": [],
    }
    save_material_unit(tmp_path / "units", _unit_record(first_id, "教材", [link(second_id, "大纲")]))
    save_material_unit(tmp_path / "units", _unit_record(second_id, "大纲", [link(third_id, "进度表")]))
    save_material_unit(tmp_path / "units", _unit_record(third_id, "进度表"))

    response = client.post(f"/api/material-units/{third_id}/references", json={"unit_ids": [first_id]})

    assert response.status_code == 422
    assert "循环引用" in response.json()["detail"]
    assert load_material_unit(tmp_path / "units", third_id)["linked_units"] == []


def test_reference_and_rename_apis_persist_changes(monkeypatch, tmp_path):
    client = _material_unit_client(monkeypatch, tmp_path)
    target_id = "b4289093-0c9a-414d-a98e-9b6f99629979"
    source_id = "73e578cf-54ee-44f2-9097-3116a072b9b7"
    save_material_unit(tmp_path / "units", _unit_record(target_id, "教材"))
    save_material_unit(tmp_path / "units", _unit_record(source_id, "大纲与进度表"))

    reference = client.post(f"/api/material-units/{target_id}/references", json={"unit_ids": [source_id]})
    renamed = client.patch(f"/api/material-units/{target_id}", json={"title": "Python课程资料单元"})

    assert reference.status_code == 200
    assert reference.json()["linked_units"][0]["unit_id"] == source_id
    assert renamed.status_code == 200
    restored = load_material_unit(tmp_path / "units", target_id)
    assert restored["title"] == "Python课程资料单元"
    assert restored["linked_unit_count"] == 1


def test_initial_outline_api_persists_teacher_edits(monkeypatch, tmp_path):
    client = _material_unit_client(monkeypatch, tmp_path)
    unit_id = "b4289093-0c9a-414d-a98e-9b6f99629979"
    save_material_unit(tmp_path / "units", _unit_record(unit_id, "Python课程资料单元"))
    outline = {
        "title": "第2次课：内置对象与运算符",
        "session": "第2次课",
        "objective": "理解常用内置对象，并能选择适当运算符解决问题。",
        "scope_summary": "第2章；2.1 常用内置对象；2.2 运算符与表达式",
        "sections": ["第2章 内置对象、运算符、表达式、关键字", "2.1 常用内置对象", "2.2 运算符与表达式"],
    }
    scope_selection = {
        "teaching_item_ids": ["schedule:unit:lesson-2"],
        "syllabus_item_ids": ["syllabus:unit:goals"],
        "outline_node_ids": ["outline:unit:chapter-2", "outline:unit:section-2-1"],
    }

    response = client.put(f"/api/material-units/{unit_id}/initial-outline", json={"outline": outline, "scope_selection": scope_selection})
    reopened = client.get(f"/api/material-units/{unit_id}")

    assert response.status_code == 200
    assert reopened.status_code == 200
    assert reopened.json()["initial_outline"] == outline
    assert reopened.json()["scope_selection"] == scope_selection


def test_merge_api_removes_source_unit_and_keeps_target(monkeypatch, tmp_path):
    client = _material_unit_client(monkeypatch, tmp_path)
    target_id = "b4289093-0c9a-414d-a98e-9b6f99629979"
    source_id = "73e578cf-54ee-44f2-9097-3116a072b9b7"
    save_material_unit(tmp_path / "units", _unit_record(target_id, "教材"))
    save_material_unit(tmp_path / "units", _unit_record(source_id, "补充资料"))

    response = client.post(
        f"/api/material-units/{target_id}/merge",
        json={"source_unit_ids": [source_id], "title": "Python课程资料单元"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Python课程资料单元"
    assert load_material_unit(tmp_path / "units", target_id)["title"] == "Python课程资料单元"
    assert not (tmp_path / "units" / f"{source_id}.json").exists()


def test_schedule_driven_match_returns_only_relevant_syllabus_categories(monkeypatch, tmp_path):
    client, unit_id = _scope_fixture(monkeypatch, tmp_path)
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()
    lesson_id = next(item["id"] for item in options["teaching_items"] if item["title"] == "第2次课")

    response = client.post(
        f"/api/material-units/{unit_id}/syllabus-matches",
        json={"teaching_item_ids": [lesson_id], "use_model": False, "limit_per_category": 3},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["matching_method"] == "deterministic"
    assert result["total_candidates"] == 8
    assert {item["category"] for item in result["matches"]} == {
        "objective", "knowledge", "key_point", "difficult_point", "practice", "assessment",
    }
    assert all("第八章" not in item["content"] and "第九章" not in item["content"] for item in result["matches"])
    assert all(item["evidence"]["material_id"] == "syllabus" for item in result["matches"])


def test_syllabus_match_model_failure_reliably_falls_back(monkeypatch, tmp_path):
    class FailingModel:
        async def generate_json(self, *_args, **_kwargs):
            raise RuntimeError("model offline")

    client, unit_id = _scope_fixture(monkeypatch, tmp_path, FailingModel())
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()
    lesson_id = options["teaching_items"][0]["id"]

    response = client.post(
        f"/api/material-units/{unit_id}/syllabus-matches",
        json={"teaching_item_ids": [lesson_id], "use_model": True},
    )

    assert response.status_code == 200
    assert response.json()["model_used"] is False
    assert response.json()["matches"]


def test_syllabus_match_model_timeout_reliably_falls_back(monkeypatch, tmp_path):
    class SlowModel:
        async def generate_json(self, *_args, **_kwargs):
            await asyncio.sleep(0.05)
            return {"matches": []}

    monkeypatch.setattr(material_unit_router, "SYLLABUS_MATCH_TIMEOUT_SECONDS", 0.01)
    client, unit_id = _scope_fixture(monkeypatch, tmp_path, SlowModel())
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()
    response = client.post(
        f"/api/material-units/{unit_id}/syllabus-matches",
        json={"teaching_item_ids": [options["teaching_items"][0]["id"]], "use_model": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_used"] is False
    assert payload["matching_method"] == "deterministic"
    assert payload["matches"]


def test_material_unit_list_and_detail_use_same_live_archive_counts(monkeypatch, tmp_path):
    client, unit_id = _scope_fixture(monkeypatch, tmp_path)
    stored = load_material_unit(tmp_path / "units", unit_id)
    stored["parsed_count"] = 0
    stored["total_characters"] = 0
    save_material_unit(tmp_path / "units", stored)

    listed = client.get("/api/material-units").json()["items"][0]
    detail = client.get(f"/api/material-units/{unit_id}").json()

    assert listed["id"] == unit_id
    assert listed["parsed_count"] == detail["parsed_count"] == len(detail["files"])
    assert listed["total_characters"] == detail["total_characters"]


def test_syllabus_match_model_can_rerank_only_known_candidates(monkeypatch, tmp_path):
    class MatchingModel:
        async def generate_json(self, _system_prompt, user_prompt):
            import json
            candidates = json.loads(user_prompt)["syllabus_candidates"]
            difficult = next(item for item in candidates if "教学难点" in item["title"])
            return {"matches": [
                {"id": difficult["id"], "category": "difficult_point", "score": 1, "reason": "与讲次主题直接对应"},
                {"id": "invented-id", "category": "objective", "score": 1, "reason": "模型虚构候选"},
            ]}

    client, unit_id = _scope_fixture(monkeypatch, tmp_path, MatchingModel())
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()
    response = client.post(f"/api/material-units/{unit_id}/syllabus-matches", json={
        "teaching_item_ids": [options["teaching_items"][0]["id"]], "use_model": True,
    })

    assert response.status_code == 200
    assert response.json()["model_used"] is True
    assert response.json()["matching_method"] == "hybrid"
    assert all(item["id"] != "invented-id" for item in response.json()["matches"])
    difficult = next(item for item in response.json()["matches"] if item["category"] == "difficult_point")
    assert "模型判断" in difficult["reason"]


def test_knowledge_outline_create_update_and_refine_preserve_versions(monkeypatch, tmp_path):
    client, unit_id = _scope_fixture(monkeypatch, tmp_path)
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()
    lesson_id = next(item["id"] for item in options["teaching_items"] if item["title"] == "第2次课")
    textbook_ids = [item["id"] for item in options["textbook_outline"] if item["title"].startswith("2.")]

    created = client.post(f"/api/material-units/{unit_id}/knowledge-outlines", json={
        "title": "第2次课知识大纲",
        "teaching_item_ids": [lesson_id],
        "outline_node_ids": textbook_ids,
        "teacher_instruction": "只整理本次课知识点",
    })
    assert created.status_code == 201
    first = created.json()
    assert first["version"] == 1
    assert all(node["evidence"] for node in first["nodes"])
    assert {item["category"] for item in first["requirements"]} >= {"objective", "key_point", "difficult_point"}

    edited_nodes = first["nodes"] + [KnowledgeNode(
        title="教师补充：变量命名边界",
        teacher_note="教师明确要求补充",
        evidence=[{"source_type": "teacher", "quote": "补充变量命名边界", "label": "教师补充"}],
    ).model_dump()]
    edited = client.put(
        f"/api/material-units/{unit_id}/knowledge-outlines/{first['id']}",
        json={"base_version": 1, "nodes": edited_nodes, "change_summary": "补充变量命名边界"},
    )
    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert edited.json()["based_on_version"] == 1

    refined = client.post(
        f"/api/material-units/{unit_id}/knowledge-outlines/{first['id']}/refine",
        json={
            "material_ids": ["guide"],
            "teacher_instruction": "结合实验指导书补充类型转换边界",
            "base_version": 2,
            "use_model": False,
        },
    )
    assert refined.status_code == 200
    third = refined.json()
    assert third["version"] == 3
    assert "guide" in third["source_material_ids"]
    added = third["nodes"][len(edited_nodes):]
    assert added
    assert all(node["evidence"] and node["evidence"][0]["material_id"] == "guide" for node in added)

    history = client.get(f"/api/material-units/{unit_id}/knowledge-outlines?include_versions=true")
    latest = client.get(f"/api/material-units/{unit_id}/knowledge-outlines/{first['id']}")
    original = client.get(f"/api/material-units/{unit_id}/knowledge-outlines/{first['id']}?version=1")
    assert [item["version"] for item in history.json()["items"]] == [3, 2, 1]
    assert latest.json()["version"] == 3
    assert original.json()["version"] == 1

    stale_update = client.put(
        f"/api/material-units/{unit_id}/knowledge-outlines/{first['id']}",
        json={"base_version": 2, "title": "过期编辑"},
    )
    stale_refine = client.post(
        f"/api/material-units/{unit_id}/knowledge-outlines/{first['id']}/refine",
        json={
            "material_ids": ["guide"],
            "teacher_instruction": "基于旧版本继续细化",
            "base_version": 2,
            "use_model": False,
        },
    )
    assert stale_update.status_code == 409
    assert stale_refine.status_code == 409


def test_refine_task_persists_status_and_result(monkeypatch, tmp_path):
    client, unit_id = _scope_fixture(monkeypatch, tmp_path)
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()
    created = client.post(f"/api/material-units/{unit_id}/knowledge-outlines", json={
        "teaching_item_ids": [options["teaching_items"][0]["id"]],
        "outline_node_ids": [options["textbook_outline"][0]["id"]],
    }).json()

    response = client.post(
        f"/api/material-units/{unit_id}/knowledge-outlines/{created['id']}/refine-tasks",
        json={
            "material_ids": ["guide"],
            "teacher_instruction": "补充类型转换边界",
            "base_version": 1,
            "use_model": False,
        },
    )
    assert response.status_code == 202
    task = response.json()
    restored = client.get(
        f"/api/material-units/{unit_id}/knowledge-outlines/{created['id']}/refine-tasks/{task['id']}"
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "completed"
    assert restored.json()["progress"] == 100
    assert restored.json()["result_version"] == 2


def test_refinement_evidence_stays_inside_selected_textbook_sections():
    material_id = "book"
    sections = [
        {"id": "chapter", "title": "第二章 数学模型", "level": 1, "preview": "章节导言"},
        {"id": "s1", "title": "第一节 概述", "level": 2, "preview": "数学模型与传递函数"},
        {"id": "s1-detail", "title": "一、数学模型", "level": 3, "preview": "输入输出关系"},
        {"id": "s2", "title": "第二节 机械系统", "level": 2, "preview": "质量阻尼弹簧"},
        {"id": "s2-detail", "title": "一、平移系统", "level": 3, "preview": "牛顿第二定律"},
        {"id": "s3", "title": "第三节 电气系统", "level": 2, "preview": "电路网络模型"},
        {"id": "s4", "title": "第四节 相似模型", "level": 2, "preview": "机电模拟"},
        {"id": "s5", "title": "第五节 一体化模型", "level": 2, "preview": "伺服系统"},
    ]
    base = {"nodes": [
        {"id": "chapter-node", "title": "第二章 数学模型", "evidence": [{"material_id": material_id, "locator": "section:chapter"}]},
        {"id": "first-node", "title": "第一节 概述", "evidence": [{"material_id": material_id, "locator": "section:s1"}]},
        {"id": "second-node", "title": "第二节 机械系统", "evidence": [{"material_id": material_id, "locator": "section:s2"}]},
        {"id": "third-node", "title": "第三节 电气系统", "evidence": [{"material_id": material_id, "locator": "section:s3"}]},
    ]}
    accessible = {material_id: {
        "material": {"id": material_id, "name": "扫描教材.pdf", "document_id": "doc-book"},
        "document": {"sections": sections}, "source_unit_id": "unit",
    }}

    evidence = refinement_evidence(base, [material_id], accessible)

    assert {item["id"] for item in evidence} == {
        "book:s1", "book:s1-detail", "book:s2", "book:s2-detail", "book:s3",
    }
    assert all("fourth" not in item["allowed_parent_ids"] for item in evidence)
    assert next(item for item in evidence if item["id"] == "book:s2-detail")["allowed_parent_ids"] == ["second-node"]


def test_refined_outline_rejects_model_nodes_outside_confirmed_scope():
    base = {
        "id": "outline", "unit_id": "unit", "version": 1, "status": "confirmed", "title": "数学模型",
        "selected_session_ids": [], "selected_syllabus_item_ids": [], "selected_textbook_node_ids": [],
        "requirements": [], "source_material_ids": ["book"], "teacher_instruction": "", "change_summary": "",
        "based_on_version": None, "created_at": "2026-08-12T01:00:00Z", "updated_at": "2026-08-12T01:00:00Z",
        "nodes": [{
            "id": "selected", "parent_id": None, "level": 1, "title": "第一节 概述", "description": "",
            "is_key_point": False, "is_difficult_point": False, "teacher_note": "",
            "evidence": [{"source_type": "textbook", "material_id": "book", "locator": "section:s1", "quote": "概述"}],
        }],
    }
    accessible = {"book": {
        "material": {"id": "book", "name": "教材.pdf", "document_id": "doc-book"},
        "document": {"sections": [
            {"id": "s1", "title": "第一节 概述", "level": 2, "preview": "数学模型概念"},
            {"id": "s1-detail", "title": "一、数学模型", "level": 3, "preview": "输入输出关系"},
            {"id": "s2", "title": "第二节 机械系统", "level": 2, "preview": "质量阻尼弹簧"},
        ]},
        "source_unit_id": "unit",
    }}
    model_nodes = [
        {"parent_node_id": "selected", "title": "数学模型的输入输出关系", "level": 2, "evidence_ids": ["book:s1-detail"]},
        {"parent_node_id": "selected", "title": "越界的机械系统", "level": 2, "evidence_ids": ["book:s2"]},
        {"parent_node_id": "unknown", "title": "虚构父节点", "level": 2, "evidence_ids": ["book:s1-detail"]},
    ]

    refined = build_refined_outline(base, ["book"], "补充当前知识点的子项", accessible, model_nodes)

    added = refined["nodes"][1:]
    assert [item["title"] for item in added] == ["数学模型的输入输出关系"]
    assert added[0]["parent_id"] == "selected"
    assert "新增 1 个" in refined["change_summary"]


def test_generic_refinement_updates_existing_nodes_without_adding_scope():
    base = {
        "id": "outline", "unit_id": "unit", "version": 1, "status": "confirmed", "title": "数学模型",
        "selected_session_ids": [], "selected_syllabus_item_ids": [], "selected_textbook_node_ids": [],
        "requirements": [], "source_material_ids": ["book"], "teacher_instruction": "", "change_summary": "",
        "based_on_version": None, "created_at": "2026-08-12T01:00:00Z", "updated_at": "2026-08-12T01:00:00Z",
        "nodes": [{
            "id": "selected", "parent_id": None, "level": 1, "title": "第一节 概述", "description": "原描述",
            "is_key_point": False, "is_difficult_point": False, "teacher_note": "",
            "evidence": [{"source_type": "textbook", "material_id": "book", "locator": "section:s1", "quote": "概述"}],
        }],
    }
    accessible = {"book": {
        "material": {"id": "book", "name": "教材.pdf", "document_id": "doc-book"},
        "document": {"sections": [
            {"id": "s1", "title": "第一节 概述", "level": 2, "preview": "数学模型概念"},
            {"id": "s1-detail", "title": "一、数学模型", "level": 3, "preview": "输入输出关系"},
            {"id": "s2", "title": "第二节 机械系统", "level": 2, "preview": "质量阻尼弹簧"},
        ]}, "source_unit_id": "unit",
    }}
    model_changes = [
        {"operation": "update", "node_id": "selected", "description": "数学模型描述输入、状态与输出之间的关系。", "evidence_ids": ["book:s1-detail"]},
        {"operation": "add", "parent_node_id": "selected", "title": "不应新增的节点", "evidence_ids": ["book:s1-detail"]},
    ]

    refined = build_refined_outline(base, ["book"], "细化知识点叙述", accessible, model_changes)

    assert len(refined["nodes"]) == 1
    assert refined["nodes"][0]["description"] == "数学模型描述输入、状态与输出之间的关系。"
    assert len(refined["nodes"][0]["evidence"]) == 2
    assert "完善 1 个知识点、新增 0 个" in refined["change_summary"]


def test_delete_knowledge_outline_version_and_history(monkeypatch, tmp_path):
    client, unit_id = _scope_fixture(monkeypatch, tmp_path)
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()
    created = client.post(f"/api/material-units/{unit_id}/knowledge-outlines", json={
        "teaching_item_ids": [options["teaching_items"][0]["id"]],
        "outline_node_ids": [options["textbook_outline"][0]["id"]],
    }).json()
    updated = client.put(
        f"/api/material-units/{unit_id}/knowledge-outlines/{created['id']}",
        json={"base_version": 1, "title": "第二版"},
    ).json()

    deleted_latest = client.delete(
        f"/api/material-units/{unit_id}/knowledge-outlines/{created['id']}?version={updated['version']}"
    )
    assert deleted_latest.status_code == 204
    latest = client.get(f"/api/material-units/{unit_id}/knowledge-outlines/{created['id']}")
    assert latest.json()["version"] == 1

    deleted_history = client.delete(
        f"/api/material-units/{unit_id}/knowledge-outlines/{created['id']}?version=1&all_history=true"
    )
    assert deleted_history.status_code == 204
    assert client.get(f"/api/material-units/{unit_id}/knowledge-outlines/{created['id']}").status_code == 404
    assert load_material_unit(tmp_path / "units", unit_id)["files"]


def test_knowledge_outline_rejects_node_without_evidence(monkeypatch, tmp_path):
    client, unit_id = _scope_fixture(monkeypatch, tmp_path)
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()

    response = client.post(f"/api/material-units/{unit_id}/knowledge-outlines", json={
        "teaching_item_ids": [options["teaching_items"][0]["id"]],
        "nodes": [{"title": "无来源知识点", "level": 1, "evidence": []}],
    })

    assert response.status_code == 422


def test_knowledge_outline_rejects_stale_scope_ids(monkeypatch, tmp_path):
    client, unit_id = _scope_fixture(monkeypatch, tmp_path)
    options = client.get(f"/api/material-units/{unit_id}/scope-options").json()

    response = client.post(f"/api/material-units/{unit_id}/knowledge-outlines", json={
        "teaching_item_ids": [options["teaching_items"][0]["id"]],
        "outline_node_ids": ["outline:removed-material:stale-node"],
    })

    assert response.status_code == 422
    assert "刷新后重新选择" in response.json()["detail"]


def test_file_reference_and_unlink_control_scope_visibility(monkeypatch, tmp_path):
    client = _material_unit_client(monkeypatch, tmp_path)
    source_archive_id = "33333333-3333-4333-8333-333333333333"
    target_archive_id = "44444444-4444-4444-8444-444444444444"
    source_id = "55555555-5555-4555-8555-555555555555"
    target_id = "66666666-6666-4666-8666-666666666666"
    source_file = _analysis_file("remote-book", "关联教材.pdf", "textbook", source_archive_id)
    source = _unit_record(source_id, "教材单元")
    source.update({
        "archive_id": source_archive_id, "archive_name": "Python", "material_ids": ["remote-book"],
        "files": [source_file], "material_count": 1, "parsed_count": 1, "total_characters": 100,
    })
    target = _unit_record(target_id, "备课单元")
    target.update({"archive_id": target_archive_id, "archive_name": "Python"})
    save_material_unit(tmp_path / "units", source)
    save_material_unit(tmp_path / "units", target)
    save_archive(tmp_path / "archives", {
        "id": source_archive_id, "name": "教材库", "course_title": "Python", "updated_at": "2026-08-12T01:00:00Z",
        "materials": [{"id": "remote-book", "name": "关联教材.pdf", "path": "关联教材.pdf", "extension": ".pdf", "category": "textbook", "parse_status": "parsed", "character_count": 100, "document_id": "doc-remote", "sha256": "remote-hash"}],
        "schedule": [], "_documents": {"remote-book": {"sections": [{"id": "c3", "title": "第3章 控制结构", "level": 1, "preview": "条件与循环"}]}},
    })
    save_archive(tmp_path / "archives", {
        "id": target_archive_id, "name": "备课库", "course_title": "Python", "updated_at": "2026-08-12T01:00:00Z",
        "materials": [], "schedule": [], "_documents": {},
    })

    linked = client.post(f"/api/material-units/{target_id}/material-references", json={
        "source_unit_id": source_id, "material_ids": ["remote-book"],
    })
    assert linked.status_code == 200
    reference_id = linked.json()["material_references"][0]["id"]
    visible = client.get(f"/api/material-units/{target_id}/scope-options")
    assert [item["title"] for item in visible.json()["textbook_outline"]] == ["第3章 控制结构"]

    removed = client.delete(f"/api/material-units/{target_id}/material-references/{reference_id}")
    hidden = client.get(f"/api/material-units/{target_id}/scope-options")
    assert removed.status_code == 200
    assert removed.json()["material_references"] == []
    assert hidden.json()["textbook_outline"] == []


def test_import_precheck_flags_unparsed_materials(monkeypatch, tmp_path: Path) -> None:
    """import-precheck 应把未完整提取的材料标记 needs_parse，用于导入前补齐解析。"""
    archive_id = "11111111-1111-4111-8111-111111111111"
    unit_id = "22222222-2222-4222-8222-222222222222"
    archive = {
        "id": archive_id, "name": "资料", "course_title": "课程", "updated_at": "2026-08-12T01:00:00Z",
        "materials": [
            {"id": "book-parsed", "name": "教材.pdf", "path": "教材.pdf", "extension": ".pdf", "category": "textbook", "parse_status": "parsed", "character_count": 100, "document_id": "doc-1", "sha256": "a"},
            {"id": "guide-metadata", "name": "实验指导.docx", "path": "实验指导.docx", "extension": ".docx", "category": "experiment", "parse_status": "metadata_only", "character_count": 0},
        ],
        "_documents": {
            "book-parsed": {"raw_text": "教材正文内容", "sections": []},
            "guide-metadata": {},
        },
    }
    record = {
        "id": unit_id, "archive_id": archive_id, "archive_name": "资料", "title": "单元",
        "material_ids": ["book-parsed", "guide-metadata"], "files": [],
        "linked_units": [], "created_at": "2026-08-12T01:00:00Z", "updated_at": "2026-08-12T01:00:00Z",
    }
    save_material_unit(tmp_path / "units", record)
    save_archive(tmp_path / "archives", archive)
    monkeypatch.setattr(material_unit_router, "load_material_unit", lambda _store, _id: load_material_unit(tmp_path / "units", _id))
    monkeypatch.setattr(material_unit_router, "load_archive", lambda _store, _id: archive)
    monkeypatch.setattr(material_unit_router, "list_material_units", lambda _store: [record])
    monkeypatch.setattr(
        material_unit_router, "get_settings",
        lambda: SimpleNamespace(
            material_unit_store_path=tmp_path / "units",
            course_archive_store_path=tmp_path / "archives",
            course_design_store_path=tmp_path / "designs",
            document_store_path=tmp_path / "documents",
        ),
    )
    api = FastAPI()
    api.include_router(material_unit_router.router)
    client = TestClient(api)

    response = client.post(f"/api/material-units/{unit_id}/import-precheck", json={"material_ids": ["book-parsed", "guide-metadata"]})

    assert response.status_code == 200
    body = response.json()
    assert body["all_parsed"] is False
    needs = body["needs_parse"]
    assert [item["material_id"] for item in needs] == ["guide-metadata"]
    parsed = next(item for item in body["items"] if item["material_id"] == "book-parsed")
    assert parsed["needs_parse"] is False
    assert parsed["parse_status"] == "parsed"
