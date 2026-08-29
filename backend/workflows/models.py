from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


RunStatus = Literal["queued", "running", "paused", "completed", "failed", "cancelled"]
TeacherDraftStatus = Literal["draft", "reviewed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgePoint(BaseModel):
    title: str
    chapter: str = ""
    is_key_point: bool = False
    difficulty_level: str = "中等"
    keywords: list[str] = Field(default_factory=list)


class DocumentSection(BaseModel):
    """可映射回原文的文档分区索引，正文通过偏移读取，避免重复存储。"""

    id: str
    title: str
    level: int = Field(default=1, ge=1, le=6)
    start_offset: int = Field(default=0, ge=0)
    end_offset: int = Field(default=0, ge=0)
    character_count: int = Field(default=0, ge=0)
    preview: str = ""
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)


class DocumentPageReport(BaseModel):
    """逐页解析结果，便于核对页覆盖、OCR 置信度和目录页码。"""

    page_number: int = Field(ge=1)
    character_count: int = Field(default=0, ge=0)
    line_count: int = Field(default=0, ge=0)
    title_count: int = Field(default=0, ge=0)
    ocr_applied: bool = False
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    source_kind: Literal["native", "scanned", "hidden_ocr"] = "native"


class DocumentExtractionReport(BaseModel):
    """文档解析质量与结构统计，供教师判断材料是否需要人工复核。"""

    format: str
    engine: str
    quality_score: int = Field(ge=0, le=100)
    quality_level: Literal["high", "medium", "low"]
    page_count: int = Field(default=0, ge=0)
    title_count: int = Field(default=0, ge=0)
    table_count: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    text_block_count: int = Field(default=0, ge=0)
    scanned_page_count: int = Field(default=0, ge=0)
    ocr_page_count: int = Field(default=0, ge=0)
    ocr_image_count: int = Field(default=0, ge=0)
    page_reports: list[DocumentPageReport] = Field(default_factory=list, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class TeachingMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    agent_name: str
    agent_type: Literal["teacher", "student", "supervisor"]
    phase: Literal[
        "design",
        "teach_knowledge",
        "student_question",
        "teacher_answer",
        "supervisor_comment",
        "iteration_complete",
    ]
    iteration: int = 0
    content: str
    level: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AgentSpec(BaseModel):
    id: str
    name: str
    role: str
    description: str
    accent: str


class WorkflowTemplate(BaseModel):
    id: str
    name: str
    description: str
    category: str
    agents: list[AgentSpec]
    review_threshold: int = Field(default=85, ge=1, le=100)


class InterventionPoint(BaseModel):
    """用户可介入的断点开关。未开启的断点不会暂停流程。"""

    after_design: bool = False
    after_question: bool = False


class TeachingScope(BaseModel):
    """教师在启动前确认的教学范围与课时边界。"""

    selected_point_titles: list[str] = Field(default_factory=list, max_length=30)
    estimated_minutes: int = Field(default=45, ge=10, le=180)
    depth: Literal["overview", "standard", "deep"] = "standard"


class PendingInput(BaseModel):
    """流程暂停时向前端描述"现在需要你做什么"。"""

    kind: Literal["design_review", "answer_choice"]
    iteration: int = 0
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


class ResumeRequest(BaseModel):
    """恢复暂停的流程。

    design_review: action=continue 直接放行；action=revise 时 content 为修改意见。
    answer_choice: action=agent 交给智能体；action=user 时 content 为用户全文；
                   action=outline 时 content 为要点，由智能体扩写。
    """

    action: Literal["continue", "revise", "agent", "user", "outline"]
    content: str = Field(default="", max_length=20000)


class ContinueRequest(BaseModel):
    """在已完成的会话上追加教学轮次。"""

    additional_iterations: int = Field(default=1, ge=1, le=3)
    context: str = Field(default="", max_length=10000)


class TeacherDraftUpdate(BaseModel):
    content: str = Field(min_length=20, max_length=200000)
    status: TeacherDraftStatus = "draft"
    base_version: int = Field(default=0, ge=0)


class TeacherSectionGenerationRequest(BaseModel):
    section_title: str = Field(min_length=1, max_length=120)
    current_content: str = Field(min_length=1, max_length=50000)
    instruction: str = Field(default="", max_length=2000)


class TeacherDraftVersion(BaseModel):
    version: int
    content: str
    status: TeacherDraftStatus
    created_at: datetime


class TeacherDraftResponse(BaseModel):
    run_id: str
    version: int
    content: str
    status: TeacherDraftStatus
    source: Literal["generated", "teacher"]
    updated_at: datetime


class TeacherDraftVersionList(BaseModel):
    items: list[TeacherDraftVersion]


class TeacherSectionGenerationResponse(BaseModel):
    section_title: str
    content: str


class CreateRunRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    archive_id: str | None = Field(default=None, max_length=36)
    design_id: str | None = Field(default=None, max_length=36)
    document_id: str | None = Field(default=None, max_length=36)
    document_name: str = Field(default="课程材料", max_length=255)
    document_text: str = Field(min_length=10, max_length=120000)
    document_sections: list[DocumentSection] = Field(default_factory=list, max_length=160)
    extraction_report: DocumentExtractionReport | None = None
    knowledge_points: list[KnowledgePoint] = Field(default_factory=list, max_length=100)
    max_iterations: int = Field(default=2, ge=1, le=5)
    context: str = Field(default="", max_length=10000)
    template_id: str = "teaching_design"
    interventions: InterventionPoint = Field(default_factory=InterventionPoint)
    scope: TeachingScope = Field(default_factory=TeachingScope)


class RunRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    template_id: str
    objective: str
    context: str = ""
    status: RunStatus = "queued"
    provider: str
    current_node: str | None = None
    final_output: str | None = None
    review: dict[str, Any] | None = None
    teaching_data: dict[str, Any] = Field(default_factory=dict)
    pending_input: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RunEvent(BaseModel):
    sequence: int = 0
    run_id: str
    event_type: str
    node: str | None = None
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class RunListResponse(BaseModel):
    items: list[RunRecord]


class EventListResponse(BaseModel):
    items: list[RunEvent]
