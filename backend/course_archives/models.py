from typing import Any, Literal

from pydantic import BaseModel, Field


MaterialCategory = Literal[
    "syllabus",
    "schedule",
    "textbook",
    "courseware",
    "lesson_plan",
    "experiment",
    "code",
    "teaching_record",
    "review",
    "interactive",
    "reference",
    "media",
    "other",
]


class ArchiveManifestItem(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    size: int = Field(default=0, ge=0)
    last_modified: int | str | None = None


class ArchiveMaterial(BaseModel):
    id: str
    path: str
    name: str
    extension: str
    size: int = Field(ge=0)
    category: MaterialCategory
    chapter: str | None = None
    lesson: str | None = None
    version: str | None = None
    sha256: str | None = None
    duplicate_group: str | None = None
    parse_status: Literal["parsed", "metadata_only", "parse_failed", "unsupported"]
    parse_message: str = ""
    document_id: str | None = None
    preview_available: bool = False
    character_count: int = Field(default=0, ge=0)
    excerpt: str = ""
    last_modified: int | str | None = None
    source_folder_id: str | None = None
    source_kind: Literal["upload", "local"] | None = None
    source_relative_path: str | None = None


class ArchiveSourceFolder(BaseModel):
    id: str
    name: str
    kind: Literal["upload", "local"]
    selection_kind: Literal["files", "folder"] = "folder"
    root_path: str | None = None
    file_count: int = Field(default=0, ge=0)
    directory_count: int = Field(default=0, ge=0)
    directory_paths: list[str] = Field(default_factory=list)
    mount_parent_id: str | None = None
    last_scanned_at: str | None = None
    created_at: str
    updated_at: str


class ArchiveChapter(BaseModel):
    key: str
    label: str
    material_ids: list[str] = Field(default_factory=list)
    material_count: int = Field(default=0, ge=0)


class ArchiveScheduleEntry(BaseModel):
    id: str
    label: str
    content: str
    chapter: str | None = None
    source_material_id: str


class PreparationHabit(BaseModel):
    key: str
    title: str
    description: str
    reusable_instruction: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class CourseArchiveSummary(BaseModel):
    id: str
    name: str
    course_title: str
    created_at: str
    updated_at: str
    total_files: int = Field(ge=0)
    parsed_files: int = Field(ge=0)
    duplicate_groups: int = Field(ge=0)
    chapter_count: int = Field(ge=0)
    categories: dict[str, int] = Field(default_factory=dict)
    academic_term: str = ""
    course_code: str = ""
    local_root: str | None = None
    last_scanned_at: str | None = None
    source_folder_count: int = Field(default=0, ge=0)


class CourseArchiveDetail(CourseArchiveSummary):
    materials: list[ArchiveMaterial] = Field(default_factory=list)
    chapters: list[ArchiveChapter] = Field(default_factory=list)
    schedule: list[ArchiveScheduleEntry] = Field(default_factory=list)
    habits: list[PreparationHabit] = Field(default_factory=list)
    preparation_profile_prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    source_folders: list[ArchiveSourceFolder] = Field(default_factory=list)


class CourseArchiveList(BaseModel):
    items: list[CourseArchiveSummary] = Field(default_factory=list)


class ArchiveDeletionImpact(BaseModel):
    archive_id: str
    course_title: str
    material_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    design_count: int = Field(ge=0)
    composition_count: int = Field(ge=0)
    run_count: int = Field(ge=0)
    layout_count: int = Field(ge=0)


class ArchiveDeletionResult(ArchiveDeletionImpact):
    deleted: bool = True


class PrepareArchiveRequest(BaseModel):
    chapter: str | None = Field(default=None, max_length=80)
    session_label: str | None = Field(default=None, max_length=160)
    material_ids: list[str] = Field(default_factory=list, max_length=40)
    primary_material_id: str | None = None


class ExtractArchiveRequest(BaseModel):
    material_ids: list[str] = Field(min_length=1, max_length=40)


class PreparationResource(BaseModel):
    id: str
    name: str
    category: MaterialCategory
    chapter: str | None = None
    role: Literal["primary", "supporting"]
    document_id: str | None = None
    preview_available: bool = False


class PreparationPack(BaseModel):
    archive_id: str
    title: str
    chapter: str | None = None
    session_label: str | None = None
    primary_material_id: str
    parsed_document: dict[str, Any]
    resources: list[PreparationResource]
    context: str
    preparation_profile_prompt: str
