from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator


ReferenceLayer = Literal["original", "extracted", "structured", "generated"]
DesignStatus = Literal["draft", "reviewed"]
AssemblySourceKind = Literal["schedule", "syllabus", "knowledge_outline", "teacher_message", "teacher_draft", "ideological", "custom"]
AssemblyTargetField = Literal[
    "session_label", "objectives", "knowledge_points", "key_points", "difficult_points",
    "methods", "tools", "ideological_elements", "teaching_process", "assessment", "postscript",
]


class CourseDataReference(BaseModel):
    id: str
    layer: ReferenceLayer
    archive_id: str
    material_id: str | None = None
    document_id: str | None = None
    source_name: str
    source_path: str = ""
    locator: str = ""
    sha256: str | None = None
    extraction_status: str = ""
    character_count: int = Field(default=0, ge=0)
    excerpt: str = ""
    original_url: str | None = None
    preview_url: str | None = None


class CourseDesignContent(BaseModel):
    course_name: str = Field(min_length=1, max_length=160)
    topic: str = Field(min_length=1, max_length=240)
    chapter: str = Field(default="", max_length=120)
    session_label: str = Field(default="", max_length=300)
    class_name: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=120)
    hours: str = Field(default="2", max_length=40)
    objectives: list[str] = Field(default_factory=list, max_length=20)
    knowledge_points: list[str] = Field(default_factory=list, max_length=240)
    key_points: list[str] = Field(default_factory=list, max_length=30)
    difficult_points: list[str] = Field(default_factory=list, max_length=20)
    methods: list[str] = Field(default_factory=list, max_length=20)
    tools: list[str] = Field(default_factory=list, max_length=20)
    ideological_elements: list[str] = Field(default_factory=list, max_length=20)
    teaching_process: str = Field(default="", max_length=100000)
    assessment: str = Field(default="", max_length=30000)
    postscript: str = Field(default="", max_length=30000)


class CourseDesignCreate(BaseModel):
    archive_id: str
    chapter: str | None = Field(default=None, max_length=120)
    schedule_id: str | None = None
    material_ids: list[str] = Field(default_factory=list, max_length=40)
    primary_material_id: str | None = None
    material_unit_id: str | None = None
    knowledge_outline_id: str | None = None
    knowledge_outline_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_knowledge_outline_reference(self) -> "CourseDesignCreate":
        if bool(self.material_unit_id) != bool(self.knowledge_outline_id):
            raise ValueError("material_unit_id 和 knowledge_outline_id 必须同时提供")
        if self.knowledge_outline_version is not None and not self.knowledge_outline_id:
            raise ValueError("指定 knowledge_outline_version 时必须提供知识大纲")
        return self


class CourseDesignKnowledgeNode(BaseModel):
    id: str = Field(default="")
    title: str = Field(min_length=1, max_length=240)
    level: int = Field(ge=1, le=6)
    description: str = Field(default="", max_length=8000)
    is_key_point: bool = False
    is_difficult_point: bool = False
    teacher_note: str = Field(default="", max_length=20000)
    evidence: list[dict] = Field(default_factory=list)


class CourseDesignKnowledgeOutline(BaseModel):
    id: str
    version: int = Field(ge=1)
    status: str
    title: str = Field(min_length=1, max_length=240)
    session: str = Field(default="", max_length=300)
    selected_session_ids: list[str] = Field(default_factory=list, max_length=20)
    knowledge_nodes: list[CourseDesignKnowledgeNode] = Field(
        default_factory=list,
        max_length=240,
        validation_alias=AliasChoices("knowledge_nodes", "nodes"),
    )
    source_references: list[dict] = Field(default_factory=list)
    scope_selection: dict = Field(default_factory=dict)
    requirements: list[dict] = Field(default_factory=list, max_length=40)
    teacher_instruction: str = Field(default="", max_length=4000)


class CourseDesignSourceSnapshot(BaseModel):
    schedule: list[dict] = Field(default_factory=list, max_length=20)
    syllabus_requirements: list[dict] = Field(default_factory=list, max_length=40)
    knowledge_nodes: list[dict] = Field(default_factory=list, max_length=240)


class CourseDesignContentInsertion(BaseModel):
    id: str
    source_id: str
    source_kind: AssemblySourceKind
    source_name: str
    locator: str = ""
    target_field: AssemblyTargetField
    mode: Literal["replace", "prepend", "append"]
    content_preview: str = Field(default="", max_length=500)
    created_at: str


class CourseDesignAssemblySource(BaseModel):
    id: str
    kind: AssemblySourceKind
    title: str
    content: str = Field(max_length=200000)
    source_name: str = ""
    locator: str = ""
    default_target: AssemblyTargetField
    iteration: int | None = Field(default=None, ge=0)
    category: str = ""


class CourseDesignAssemblySourceList(BaseModel):
    design_id: str
    run_id: str | None = None
    items: list[CourseDesignAssemblySource] = Field(default_factory=list)


class CourseDesignAssemblyApply(BaseModel):
    base_version: int = Field(ge=1)
    source_ids: list[str] = Field(default_factory=list, max_length=80)
    target_field: AssemblyTargetField
    mode: Literal["replace", "prepend", "append"] = "append"
    custom_content: str = Field(default="", max_length=200000)
    custom_title: str = Field(default="教师补充", max_length=160)

    @model_validator(mode="after")
    def validate_content_source(self) -> "CourseDesignAssemblyApply":
        if not self.source_ids and not self.custom_content.strip():
            raise ValueError("至少选择一项来源内容或填写自定义内容")
        return self


class CourseDesignUpdate(BaseModel):
    content: CourseDesignContent
    status: DesignStatus = "draft"
    base_version: int = Field(ge=1)
    template_document_id: str | None = None
    template_material_id: str | None = None


class CourseDesignRecord(BaseModel):
    id: str
    title: str
    archive_id: str
    chapter: str | None = None
    schedule_id: str | None = None
    primary_material_id: str
    material_ids: list[str] = Field(default_factory=list)
    material_unit_id: str | None = None
    knowledge_outline_id: str | None = None
    knowledge_outline_version: int | None = None
    outline_has_newer_version: bool = False
    outline_latest_version: int | None = None
    run_id: str | None = None
    status: DesignStatus = "draft"
    version: int = Field(default=1, ge=1)
    template_document_id: str | None = None
    template_material_id: str | None = None
    source_snapshot: CourseDesignSourceSnapshot = Field(default_factory=CourseDesignSourceSnapshot)
    content_insertions: list[CourseDesignContentInsertion] = Field(default_factory=list)
    source_references: list[CourseDataReference] = Field(default_factory=list)
    exports: list["CourseDesignExportRecord"] = Field(default_factory=list)
    content: CourseDesignContent
    created_at: str
    updated_at: str


class CourseDesignSummary(BaseModel):
    id: str
    title: str
    archive_id: str
    chapter: str | None = None
    run_id: str | None = None
    status: DesignStatus
    version: int
    source_count: int = Field(ge=0)
    export_count: int = Field(default=0, ge=0)
    latest_export_at: str | None = None
    updated_at: str


class CourseDesignList(BaseModel):
    items: list[CourseDesignSummary] = Field(default_factory=list)


class CourseDesignVersion(BaseModel):
    version: int
    status: DesignStatus
    content: CourseDesignContent
    template_document_id: str | None = None
    template_material_id: str | None = None
    content_insertions: list[CourseDesignContentInsertion] = Field(default_factory=list)
    created_at: str


class CourseDesignVersionList(BaseModel):
    items: list[CourseDesignVersion] = Field(default_factory=list)


class CourseDesignExportRequest(BaseModel):
    template_material_id: str | None = None
    template_document_id: str | None = None
    filename: str | None = Field(default=None, max_length=180)
    preserve_source_format: bool = True


class CourseDesignTemplateInspection(BaseModel):
    template_mode: Literal["source-template", "standard-template"]
    compatible: bool
    matched_fields: list[str] = Field(default_factory=list)
    unmatched_fields: list[str] = Field(default_factory=list)
    replacement_count: int = Field(default=0, ge=0)
    paragraph_count: int = Field(default=0, ge=0)
    table_count: int = Field(default=0, ge=0)
    header_count: int = Field(default=0, ge=0)
    footer_count: int = Field(default=0, ge=0)
    message: str = ""


class CourseDesignExportRecord(BaseModel):
    id: str
    design_id: str
    design_version: int = Field(ge=1)
    filename: str
    document_id: str
    template_mode: Literal["source-template", "standard-template"]
    template_document_id: str | None = None
    template_material_id: str | None = None
    template_name: str = ""
    matched_fields: list[str] = Field(default_factory=list)
    sha256: str
    size: int = Field(ge=1)
    preview_url: str
    download_url: str
    created_at: str


class CourseDesignExportList(BaseModel):
    items: list[CourseDesignExportRecord] = Field(default_factory=list)


class CourseReferenceDetail(BaseModel):
    reference: CourseDataReference
    content: str = ""
    sections: list[dict] = Field(default_factory=list)
