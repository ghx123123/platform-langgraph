from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


SyllabusRequirementCategory = Literal[
    "objective",
    "knowledge",
    "key_point",
    "difficult_point",
    "practice",
    "assessment",
]
EvidenceSourceType = Literal["schedule", "syllabus", "textbook", "material", "teacher"]


class MaterialUnitCreate(BaseModel):
    archive_id: str
    title: str = Field(min_length=1, max_length=160)
    material_ids: list[str] = Field(min_length=1, max_length=40)
    # S3: 导入资料单元时是否立即做完整正文提取(含OCR/布局) — 默认 False=快速登记
    # 完整提取由"知识大纲"步骤按需进行
    extract_immediately: bool = False


class MaterialUnitAppend(BaseModel):
    material_ids: list[str] = Field(min_length=1, max_length=40)
    # S3: 追加到资料单元时是否立即完整提取正文 — 默认 False=快速登记
    extract_immediately: bool = False


class MaterialUnitRename(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class MaterialUnitReferenceRequest(BaseModel):
    unit_ids: list[str] = Field(min_length=1, max_length=20)


class MaterialUnitFileReferenceRequest(BaseModel):
    source_unit_id: str
    material_ids: list[str] = Field(min_length=1, max_length=40)


class MaterialUnitMergeRequest(BaseModel):
    source_unit_ids: list[str] = Field(min_length=1, max_length=20)
    title: str | None = Field(default=None, max_length=160)


class MaterialUnitFileAnalysis(BaseModel):
    material_id: str
    name: str
    path: str
    category: str
    extension: str
    document_id: str | None = None
    preview_available: bool = False
    parse_status: Literal["parsed", "metadata_only", "parse_failed", "unsupported"]
    parse_message: str = ""
    character_count: int = Field(default=0, ge=0)
    summary: str = ""
    section_count: int = Field(default=0, ge=0)
    knowledge_points: list[str] = Field(default_factory=list)
    extraction_engine: str = ""
    quality_level: str = ""
    archive_id: str | None = None
    source_unit_id: str | None = None


class MaterialUnitFileReference(BaseModel):
    id: str
    source_unit_id: str
    source_unit_title: str
    archive_id: str
    archive_name: str = ""
    material_id: str
    file: MaterialUnitFileAnalysis


class MaterialUnitSummary(BaseModel):
    id: str
    archive_id: str
    archive_name: str
    title: str
    material_count: int = Field(ge=0)
    parsed_count: int = Field(ge=0)
    total_characters: int = Field(ge=0)
    overview: str = ""
    key_points: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    linked_unit_count: int = Field(default=0, ge=0)
    source_category_counts: dict[str, int] = Field(default_factory=dict)


class MaterialUnitLink(BaseModel):
    unit_id: str
    title: str
    archive_id: str
    archive_name: str
    material_count: int = Field(default=0, ge=0)
    files: list[MaterialUnitFileAnalysis] = Field(default_factory=list)


class MaterialUnitInitialOutline(BaseModel):
    title: str
    session: str = ""
    objective: str = ""
    scope_summary: str = ""
    sections: list[str] = Field(default_factory=list)


class MaterialUnitScopeSelection(BaseModel):
    teaching_item_ids: list[str] = Field(default_factory=list, max_length=20)
    syllabus_item_ids: list[str] = Field(default_factory=list, max_length=20)
    outline_node_ids: list[str] = Field(default_factory=list, max_length=80)


class MaterialUnitRecord(MaterialUnitSummary):
    material_ids: list[str] = Field(default_factory=list)
    files: list[MaterialUnitFileAnalysis] = Field(default_factory=list)
    linked_units: list[MaterialUnitLink] = Field(default_factory=list)
    material_references: list[MaterialUnitFileReference] = Field(default_factory=list)
    initial_outline: MaterialUnitInitialOutline | None = None
    scope_selection: MaterialUnitScopeSelection = Field(default_factory=MaterialUnitScopeSelection)
    knowledge_outlines: list["KnowledgeOutline"] = Field(default_factory=list)


class MaterialUnitList(BaseModel):
    items: list[MaterialUnitSummary] = Field(default_factory=list)


class MaterialUnitScopeOption(BaseModel):
    id: str
    title: str
    content: str = ""
    source_material_id: str = ""
    source_unit_id: str = ""
    source_name: str = ""
    document_id: str | None = None
    source_hash: str | None = None
    locator: str = ""


class MaterialUnitOutlineNode(BaseModel):
    id: str
    title: str
    level: int = Field(ge=1, le=3)
    preview: str = ""
    source_material_id: str = ""
    source_unit_id: str = ""
    source_name: str = ""
    document_id: str | None = None
    source_hash: str | None = None
    locator: str = ""


class MaterialUnitScopeOptions(BaseModel):
    unit_id: str
    course_title: str
    teaching_items: list[MaterialUnitScopeOption] = Field(default_factory=list)
    syllabus_items: list[MaterialUnitScopeOption] = Field(default_factory=list)
    textbook_outline: list[MaterialUnitOutlineNode] = Field(default_factory=list)


class MaterialUnitScopeRequest(BaseModel):
    teaching_item_ids: list[str] = Field(default_factory=list, max_length=20)
    syllabus_item_ids: list[str] = Field(default_factory=list, max_length=20)
    outline_node_ids: list[str] = Field(default_factory=list, max_length=80)
    title: str = Field(default="", max_length=160)


class MaterialUnitOutlineSave(BaseModel):
    outline: MaterialUnitInitialOutline
    scope_selection: MaterialUnitScopeSelection = Field(default_factory=MaterialUnitScopeSelection)


class SyllabusMatchRequest(BaseModel):
    teaching_item_ids: list[str] = Field(min_length=1, max_length=20)
    use_model: bool = True
    limit_per_category: int = Field(default=4, ge=1, le=8)


class KnowledgeEvidence(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_type: EvidenceSourceType
    material_id: str = ""
    source_unit_id: str = ""
    document_id: str | None = None
    source_hash: str | None = None
    locator: str = ""
    quote: str = Field(min_length=1, max_length=1200)
    label: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def validate_traceable_source(self) -> "KnowledgeEvidence":
        if self.source_type != "teacher" and not self.material_id:
            raise ValueError("Document evidence must include material_id")
        return self


class SyllabusMatchItem(BaseModel):
    id: str
    category: SyllabusRequirementCategory
    category_label: str
    title: str
    content: str
    score: float = Field(ge=0, le=1)
    reason: str
    recommended: bool = False
    evidence: KnowledgeEvidence


class SyllabusMatchResponse(BaseModel):
    unit_id: str
    teaching_items: list[MaterialUnitScopeOption] = Field(default_factory=list)
    matches: list[SyllabusMatchItem] = Field(default_factory=list)
    total_candidates: int = Field(default=0, ge=0)
    matching_method: Literal["deterministic", "hybrid"] = "deterministic"
    model_used: bool = False


class KnowledgeNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    parent_id: str | None = None
    level: int = Field(default=1, ge=1, le=3)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=8000)
    is_key_point: bool = False
    is_difficult_point: bool = False
    teacher_note: str = Field(default="", max_length=20000)
    evidence: list[KnowledgeEvidence] = Field(min_length=1, max_length=20)


class KnowledgeOutline(BaseModel):
    id: str
    unit_id: str
    version: int = Field(ge=1)
    status: Literal["draft", "confirmed"] = "draft"
    title: str = Field(min_length=1, max_length=160)
    selected_session_ids: list[str] = Field(default_factory=list, max_length=20)
    selected_syllabus_item_ids: list[str] = Field(default_factory=list, max_length=40)
    selected_textbook_node_ids: list[str] = Field(default_factory=list, max_length=80)
    requirements: list[SyllabusMatchItem] = Field(default_factory=list, max_length=40)
    nodes: list[KnowledgeNode] = Field(min_length=1, max_length=240)
    source_material_ids: list[str] = Field(default_factory=list, max_length=80)
    teacher_instruction: str = Field(default="", max_length=4000)
    change_summary: str = Field(default="", max_length=1000)
    based_on_version: int | None = Field(default=None, ge=1)
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_node_hierarchy(self) -> "KnowledgeOutline":
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Knowledge node ids must be unique")
        for node in self.nodes:
            if node.parent_id and node.parent_id not in node_ids:
                raise ValueError("Knowledge node parent_id must reference a node in the same outline")
        return self


class KnowledgeOutlineCreate(BaseModel):
    title: str = Field(default="", max_length=160)
    teaching_item_ids: list[str] = Field(min_length=1, max_length=20)
    syllabus_item_ids: list[str] = Field(default_factory=list, max_length=40)
    outline_node_ids: list[str] = Field(default_factory=list, max_length=80)
    nodes: list[KnowledgeNode] = Field(default_factory=list, max_length=240)
    status: Literal["draft", "confirmed"] = "draft"
    teacher_instruction: str = Field(default="", max_length=4000)


class KnowledgeOutlineUpdate(BaseModel):
    base_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: Literal["draft", "confirmed"] | None = None
    nodes: list[KnowledgeNode] | None = Field(default=None, min_length=1, max_length=240)
    teacher_instruction: str | None = Field(default=None, max_length=4000)
    change_summary: str = Field(default="教师编辑", max_length=1000)


class KnowledgeOutlineRefineRequest(BaseModel):
    # 允许空列表: material_ids=[] 且 teacher_instruction 非空 → 自由扩展模式(仅凭教师提示词优化当前大纲)
    material_ids: list[str] = Field(default_factory=list, max_length=40)
    teacher_instruction: str = Field(min_length=2, max_length=4000)
    base_version: int | None = Field(default=None, ge=1)
    use_model: bool = True


RefineTaskStatus = Literal[
    "queued", "loading_sources", "analyzing", "generating", "saving", "completed", "failed",
]


class KnowledgeOutlineRefineTask(BaseModel):
    id: str
    unit_id: str
    outline_id: str
    base_version: int = Field(ge=1)
    status: RefineTaskStatus = "queued"
    stage_label: str = "任务已进入队列"
    progress: int = Field(default=0, ge=0, le=100)
    material_ids: list[str] = Field(default_factory=list, max_length=40)
    teacher_instruction: str = Field(min_length=2, max_length=4000)
    use_model: bool = True
    result_version: int | None = Field(default=None, ge=1)
    error: str = ""
    created_at: str
    started_at: str | None = None
    updated_at: str
    finished_at: str | None = None
    elapsed_seconds: int = Field(default=0, ge=0)


class KnowledgeOutlineRefineTaskList(BaseModel):
    items: list[KnowledgeOutlineRefineTask] = Field(default_factory=list)


class KnowledgeOutlineList(BaseModel):
    items: list[KnowledgeOutline] = Field(default_factory=list)
