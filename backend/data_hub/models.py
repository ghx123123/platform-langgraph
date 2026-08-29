from typing import Literal

from pydantic import BaseModel, Field


BlockKind = Literal[
    "original", "extracted", "teaching_design", "student_question",
    "teacher_answer", "supervisor_review", "ideological_element", "imported",
]


class DataHubStats(BaseModel):
    terms: int = Field(ge=0)
    courses: int = Field(ge=0)
    units: int = Field(ge=0)
    materials: int = Field(ge=0)
    generated_blocks: int = Field(ge=0)


class DataHubUnit(BaseModel):
    id: str
    archive_id: str
    archive_name: str
    academic_term: str = "未设置学期"
    course_title: str
    course_code: str = ""
    chapter: str = "全课程"
    material_count: int = Field(ge=0)
    parsed_count: int = Field(ge=0)
    design_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    updated_at: str


class DataHubBlock(BaseModel):
    id: str
    kind: BlockKind
    title: str
    content_preview: str = ""
    content: str = ""
    archive_id: str | None = None
    unit_id: str | None = None
    design_id: str | None = None
    run_id: str | None = None
    source_name: str = ""
    locator: str = ""
    original_url: str | None = None
    preview_url: str | None = None
    folder_id: str | None = None
    editable: bool = False
    updated_at: str = ""
    category: str = "other"
    modified_at: int | str | None = None
    source_folder_id: str | None = None
    source_kind: Literal["upload", "local"] | None = None
    source_selection_kind: Literal["files", "folder"] | None = None


class DataHubFolder(BaseModel):
    id: str
    unit_id: str
    name: str
    parent_id: str | None = None
    system_parent: BlockKind | None = None
    created_at: str
    updated_at: str
    source_folder_id: str | None = None
    source_kind: Literal["upload", "local"] | None = None
    source_selection_kind: Literal["files", "folder"] | None = None
    source_path: str | None = None
    last_scanned_at: str | None = None


class DataHubCatalog(BaseModel):
    stats: DataHubStats
    terms: list[str] = Field(default_factory=list)
    courses: list[str] = Field(default_factory=list)
    units: list[DataHubUnit] = Field(default_factory=list)
    folders: list[DataHubFolder] = Field(default_factory=list)
    blocks: list[DataHubBlock] = Field(default_factory=list)


class DataHubLayout(BaseModel):
    unit_id: str
    folders: list[DataHubFolder] = Field(default_factory=list)
    placements: dict[str, str] = Field(default_factory=dict)
    titles: dict[str, str] = Field(default_factory=dict)
    updated_at: str = ""


class FolderCreate(BaseModel):
    unit_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None
    system_parent: BlockKind | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    move: bool = False
    parent_id: str | None = None
    system_parent: BlockKind | None = None


class DataHubBlockUpdate(BaseModel):
    unit_id: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    move: bool = False
    folder_id: str | None = None


class DataHubBlocksMove(BaseModel):
    unit_id: str = Field(min_length=1, max_length=120)
    block_ids: list[str] = Field(min_length=1, max_length=100)
    folder_id: str | None = None


class LocalMaterialTransferRequest(BaseModel):
    unit_id: str = Field(min_length=1, max_length=120)
    block_ids: list[str] = Field(min_length=1, max_length=100)
    destination_folder_id: str = Field(min_length=1, max_length=120)
    operation: Literal["copy", "move"]


class LocalFolderSyncRequest(BaseModel):
    unit_id: str = Field(min_length=1, max_length=120)
    folder_id: str = Field(min_length=1, max_length=120)


class LocalSyncResult(BaseModel):
    archive_id: str
    unit_id: str
    source_id: str
    synced_files: int = Field(default=0, ge=0)
    created_directories: int = Field(default=0, ge=0)
    message: str


class LocalSourceDiffItem(BaseModel):
    path: str
    kind: Literal["file", "directory"]
    status: Literal[
        "local_added", "local_removed", "local_changed", "platform_deleted",
        "local_directory_added", "platform_directory_added",
    ]
    local_size: int | None = Field(default=None, ge=0)
    platform_size: int | None = Field(default=None, ge=0)
    can_restore: bool = False


class LocalSourceDiffResult(BaseModel):
    archive_id: str
    source_id: str
    source_name: str
    local_root: str
    items: list[LocalSourceDiffItem] = Field(default_factory=list)
    local_changes: int = Field(default=0, ge=0)
    platform_changes: int = Field(default=0, ge=0)
    blocked_restores: int = Field(default=0, ge=0)
    checked_at: str


class LocalSourceReconcileRequest(BaseModel):
    direction: Literal["update_platform", "update_local"]


class LocalSourceReconcileResult(BaseModel):
    archive_id: str
    source_id: str
    direction: Literal["update_platform", "update_local"]
    applied: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    message: str


class DataHubBlocksDelete(BaseModel):
    unit_id: str = Field(min_length=1, max_length=120)
    block_ids: list[str] = Field(min_length=1, max_length=100)


class DataHubUploadResult(BaseModel):
    archive_id: str
    unit_id: str
    material_count: int = Field(ge=0)
    folder_count: int = Field(ge=0)


class ImportFolderOrganizeRequest(BaseModel):
    folder_name: str = Field(min_length=1, max_length=120)


class ImportFolderOrganizeResult(BaseModel):
    archive_id: str
    unit_count: int = Field(ge=0)
    folder_count: int = Field(ge=0)
    block_count: int = Field(ge=0)


class ArchiveMetadataUpdate(BaseModel):
    academic_term: str = Field(default="", max_length=80)
    course_title: str = Field(min_length=1, max_length=160)
    course_code: str = Field(default="", max_length=80)


class LibraryRootCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class LibraryRootUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AcademicTermRename(BaseModel):
    current_name: str = Field(min_length=1, max_length=80)
    new_name: str = Field(min_length=1, max_length=80)


class AcademicTermRenameResult(BaseModel):
    previous_name: str
    academic_term: str
    updated_courses: int = Field(ge=1)


class LocalSourceScanRequest(BaseModel):
    root_path: str = Field(min_length=1, max_length=1000)
    archive_id: str | None = None
    archive_name: str = Field(default="", max_length=100)
    academic_term: str = Field(default="", max_length=80)
    course_title: str = Field(default="", max_length=160)
    course_code: str = Field(default="", max_length=80)
    source_id: str | None = None
    source_name: str = Field(default="", max_length=160)


class LocalSourceChangeSet(BaseModel):
    added: int = Field(ge=0)
    changed: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    removed: int = Field(ge=0)
    parsed: int = Field(ge=0)


class LocalSourceScanResult(BaseModel):
    archive_id: str
    archive_name: str
    local_root: str
    changes: LocalSourceChangeSet
    total_files: int = Field(ge=0)
    total_directories: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    source_id: str
    source_name: str
    source_kind: Literal["local", "upload"] = "local"


class BrowserSourceManifestItem(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    size: int = Field(default=0, ge=0)
    last_modified: int | str | None = None


class BrowserSourceRegisterRequest(BaseModel):
    archive_id: str | None = None
    source_id: str | None = None
    source_name: str = Field(min_length=1, max_length=160)
    academic_term: str = Field(default="", max_length=80)
    course_title: str = Field(default="", max_length=160)
    course_code: str = Field(default="", max_length=80)
    selection_kind: Literal["files", "folder"] = "folder"
    manifest: list[BrowserSourceManifestItem] = Field(default_factory=list, max_length=6000)
    directories: list[str] = Field(default_factory=list, max_length=6000)
    parent_folder_id: str | None = None


class SourceFolderRecord(BaseModel):
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


class SourceFolderResult(BaseModel):
    archive_id: str
    source: SourceFolderRecord
    changes: LocalSourceChangeSet
    total_files: int = Field(ge=0)


class SourceUploadResult(BaseModel):
    archive_id: str
    source_id: str
    uploaded: int = Field(ge=0)
    total_files: int = Field(ge=0)


class ExternalOpenResult(BaseModel):
    opened: bool = True
    target: str
    message: str


class MaterialReloadResult(BaseModel):
    archive_id: str
    material_id: str
    reloaded: bool
    updated_at: str


class CompositionBlock(BaseModel):
    id: str
    source_block_id: str | None = None
    kind: BlockKind
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(default="", max_length=200000)
    source_name: str = ""
    locator: str = ""


class CompositionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    archive_id: str | None = None
    unit_id: str | None = None
    blocks: list[CompositionBlock] = Field(default_factory=list, max_length=100)


class CompositionUpdate(CompositionCreate):
    base_version: int = Field(ge=1)


class CompositionRecord(CompositionCreate):
    id: str
    version: int = Field(ge=1)
    created_at: str
    updated_at: str
    import_document_id: str | None = None
    import_original_url: str | None = None
    import_preview_url: str | None = None


class CompositionSummary(BaseModel):
    id: str
    title: str
    archive_id: str | None = None
    unit_id: str | None = None
    version: int = Field(ge=1)
    block_count: int = Field(ge=0)
    updated_at: str


class CompositionList(BaseModel):
    items: list[CompositionSummary] = Field(default_factory=list)
