export type RunStatus = 'queued' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';

export interface InterventionPoint {
  after_design: boolean;
  after_question: boolean;
}

export type TeachingDepth = 'overview' | 'standard' | 'deep';

export interface TeachingScope {
  selected_point_titles: string[];
  estimated_minutes: number;
  depth: TeachingDepth;
}

export interface PendingInput {
  kind: 'design_review' | 'answer_choice';
  iteration: number;
  prompt: string;
  context: {
    learning_objectives?: string[];
    stages?: Array<{ name: string; purpose: string; activity: string; minutes: number }>;
    questions?: Array<{ agent_name: string; level?: 'high' | 'medium' | 'low'; content: string }>;
  };
}

export interface ResumeInput {
  action: 'continue' | 'revise' | 'agent' | 'user' | 'outline';
  content: string;
}

export interface AgentSpec {
  id: string;
  name: string;
  role: string;
  description: string;
  accent: string;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  agents: AgentSpec[];
  review_threshold: number;
}

export interface KnowledgePoint {
  title: string;
  chapter: string;
  is_key_point: boolean;
  difficulty_level: string;
  keywords: string[];
}

export interface DocumentSection {
  id: string;
  title: string;
  level: number;
  start_offset: number;
  end_offset: number;
  character_count: number;
  preview: string;
  page_start?: number | null;
  page_end?: number | null;
}

export interface SectionInsight {
  section_id: string;
  title: string;
  relevance: 'core' | 'support' | 'context';
  matched_points: string[];
  related_concepts: string[];
  evidence: string;
  status: 'analyzed';
}

export interface DocumentCoverage {
  total_sections: number;
  analyzed_sections: number;
  coverage_percent: number;
  focused_sections: number;
  support_sections: number;
  context_sections: number;
  method: string;
}

export interface DocumentExtractionReport {
  format: string;
  engine: string;
  quality_score: number;
  quality_level: 'high' | 'medium' | 'low';
  page_count: number;
  title_count: number;
  table_count: number;
  image_count: number;
  text_block_count: number;
  scanned_page_count: number;
  ocr_page_count?: number;
  ocr_image_count?: number;
  page_reports?: Array<{
    page_number: number;
    character_count: number;
    line_count: number;
    title_count: number;
    ocr_applied: boolean;
    ocr_confidence?: number | null;
    source_kind: 'native' | 'scanned' | 'hidden_ocr';
  }>;
  warnings: string[];
}

export type VisualAnalysisBudget = 'small' | 'normal' | 'large';

export interface DocumentVisualAnalysis {
  page_number: number;
  status: 'completed' | 'dry_run';
  model: string;
  budget: VisualAnalysisBudget;
  image_width: number;
  image_height: number;
  image_bytes: number;
  response_ms: number;
  summary: string;
  visual_elements: Array<{
    type: 'diagram' | 'chart' | 'table' | 'formula' | 'image' | 'layout' | 'other';
    title: string;
    description: string;
  }>;
  teaching_notes: string[];
  ocr_corrections: Array<{
    recognized: string;
    corrected: string;
    evidence: string;
  }>;
  confidence: number;
  warnings: string[];
  analyzed_at: string;
}

export interface DocumentVisualAnalysisRequest {
  page_number: number;
  budget: VisualAnalysisBudget;
  extracted_text: string;
  dry_run?: boolean;
}

export interface TeachingMessage {
  id: string;
  agent_id: string;
  agent_name: string;
  agent_type: 'teacher' | 'student' | 'supervisor';
  phase: TeachingPhase;
  iteration: number;
  content: string;
  level?: 'high' | 'medium' | 'low';
  created_at: string;
}

export type TeachingPhase = 'design' | 'teach_knowledge' | 'student_question' | 'teacher_answer' | 'supervisor_comment' | 'iteration_complete';

export interface TeachingData {
  archive_id?: string;
  design_id?: string;
  document_id?: string;
  document_name?: string;
  document_text?: string;
  document_sections?: DocumentSection[];
  extraction_report?: DocumentExtractionReport;
  knowledge_points?: KnowledgePoint[];
  content_analysis?: {
    summary?: string;
    key_points?: string[];
    difficult_points?: string[];
    prerequisites?: string[];
    learner_misconceptions?: string[];
    section_insights?: SectionInsight[];
    document_coverage?: DocumentCoverage;
  };
  teaching_framework?: {
    learning_objectives?: string[];
    stages?: Array<{ name: string; purpose: string; activity: string; minutes: number }>;
    strategies?: string[];
    assessment?: string[];
    ideological_elements?: Array<{ dimension: string; content: string; integration_method: string }>;
    exercises?: Array<{ level: 'low' | 'medium' | 'high'; question: string; answer: string }>;
    iteration_prompt?: string;
  };
  messages?: TeachingMessage[];
  current_iteration?: number;
  max_iterations?: number;
  interventions?: InterventionPoint;
  scope?: TeachingScope;
}

export interface WorkflowRun {
  id: string;
  thread_id: string;
  template_id: string;
  objective: string;
  context: string;
  status: RunStatus;
  provider: string;
  current_node?: string;
  final_output?: string;
  review?: SupervisorReview;
  teaching_data: TeachingData;
  pending_input?: PendingInput | null;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface SupervisorReview {
  score?: number;
  dimensions?: Record<string, number>;
  strengths?: string[];
  weaknesses?: string[];
  suggestions?: string[];
  next_focus?: string;
  iteration_prompt?: string;
}

export interface RunEvent {
  sequence: number;
  run_id: string;
  event_type: string;
  node?: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ParsedDocument {
  document_id: string;
  file_name: string;
  course_name: string;
  raw_text: string;
  knowledge_points: KnowledgePoint[];
  sections?: DocumentSection[];
  extraction_report?: DocumentExtractionReport;
  character_count: number;
  processed_character_count?: number;
  is_truncated?: boolean;
}

export interface CreateRunInput {
    title: string;
    archive_id?: string;
    design_id?: string;
    document_id?: string;
  document_name: string;
  document_text: string;
  document_sections: DocumentSection[];
  extraction_report?: DocumentExtractionReport;
  knowledge_points: KnowledgePoint[];
  max_iterations: number;
  context: string;
  template_id: 'teaching_design';
  interventions: InterventionPoint;
  scope: TeachingScope;
}

export type ArchiveMaterialCategory =
  | 'syllabus' | 'schedule' | 'textbook' | 'courseware' | 'lesson_plan'
  | 'experiment' | 'code' | 'teaching_record' | 'review' | 'interactive'
  | 'reference' | 'media' | 'other';

export interface CourseArchiveMaterial {
  id: string;
  path: string;
  name: string;
  extension: string;
  size: number;
  category: ArchiveMaterialCategory;
  chapter?: string | null;
  lesson?: string | null;
  version?: string | null;
  sha256?: string | null;
  duplicate_group?: string | null;
  parse_status: 'parsed' | 'metadata_only' | 'parse_failed' | 'unsupported';
  parse_message: string;
  document_id?: string | null;
  preview_available: boolean;
  character_count: number;
  excerpt: string;
  last_modified?: number | string | null;
  source_folder_id?: string | null;
  source_kind?: 'upload' | 'local' | null;
  source_relative_path?: string | null;
}

export interface CourseArchiveChapter {
  key: string;
  label: string;
  material_ids: string[];
  material_count: number;
}

export interface CourseArchiveScheduleEntry {
  id: string;
  label: string;
  content: string;
  chapter?: string | null;
  source_material_id: string;
}

export interface PreparationHabit {
  key: string;
  title: string;
  description: string;
  reusable_instruction: string;
  evidence: string[];
  confidence: number;
}

export interface CourseArchiveSummary {
  id: string;
  name: string;
  course_title: string;
  created_at: string;
  updated_at: string;
  total_files: number;
  parsed_files: number;
  duplicate_groups: number;
  chapter_count: number;
  categories: Record<string, number>;
  academic_term: string;
  course_code: string;
  local_root?: string | null;
  last_scanned_at?: string | null;
  source_folder_count: number;
}

export interface ArchiveSourceFolder {
  id: string;
  name: string;
  kind: 'upload' | 'local';
  selection_kind?: 'files' | 'folder';
  root_path?: string | null;
  file_count: number;
  directory_count?: number;
  directory_paths?: string[];
  mount_parent_id?: string | null;
  last_scanned_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArchiveDeletionImpact {
  archive_id: string;
  course_title: string;
  material_count: number;
  document_count: number;
  design_count: number;
  composition_count: number;
  run_count: number;
  layout_count: number;
}

export interface ArchiveDeletionResult extends ArchiveDeletionImpact {
  deleted: boolean;
}

export interface CourseArchiveDetail extends CourseArchiveSummary {
  materials: CourseArchiveMaterial[];
  chapters: CourseArchiveChapter[];
  schedule: CourseArchiveScheduleEntry[];
  habits: PreparationHabit[];
  preparation_profile_prompt: string;
  warnings: string[];
  source_folders: ArchiveSourceFolder[];
}

export interface PrepareArchiveInput {
  chapter?: string | null;
  schedule_id?: string | null;
  session_label?: string | null;
  material_ids: string[];
  primary_material_id?: string | null;
}

export interface PreparationPack {
  archive_id: string;
  title: string;
  chapter?: string | null;
  session_label?: string | null;
  primary_material_id: string;
  parsed_document: ParsedDocument;
  resources: Array<{
    id: string;
    name: string;
    category: ArchiveMaterialCategory;
    chapter?: string | null;
    role: 'primary' | 'supporting';
    document_id?: string | null;
    preview_available: boolean;
  }>;
  context: string;
  preparation_profile_prompt: string;
}

export type CourseDesignStatus = 'draft' | 'reviewed';
export type CourseReferenceLayer = 'original' | 'extracted' | 'structured' | 'generated';

export interface CourseDataReference {
  id: string;
  layer: CourseReferenceLayer;
  archive_id: string;
  material_id?: string | null;
  document_id?: string | null;
  source_name: string;
  source_path: string;
  locator: string;
  sha256?: string | null;
  extraction_status: string;
  character_count: number;
  excerpt: string;
  original_url?: string | null;
  preview_url?: string | null;
}

export interface CourseDesignContent {
  course_name: string;
  topic: string;
  chapter: string;
  session_label: string;
  class_name: string;
  location: string;
  hours: string;
  objectives: string[];
  knowledge_points: string[];
  key_points: string[];
  difficult_points: string[];
  methods: string[];
  tools: string[];
  ideological_elements: string[];
  teaching_process: string;
  assessment: string;
  postscript: string;
}

export type CourseDesignAssemblySourceKind = 'schedule' | 'syllabus' | 'knowledge_outline' | 'teacher_message' | 'teacher_draft' | 'ideological' | 'custom';
export type CourseDesignAssemblyTarget = 'session_label' | 'objectives' | 'knowledge_points' | 'key_points' | 'difficult_points' | 'methods' | 'tools' | 'ideological_elements' | 'teaching_process' | 'assessment' | 'postscript';

export interface CourseDesignAssemblySource {
  id: string;
  kind: CourseDesignAssemblySourceKind;
  title: string;
  content: string;
  source_name: string;
  locator: string;
  default_target: CourseDesignAssemblyTarget;
  iteration?: number | null;
  category: string;
}

export interface CourseDesignContentInsertion {
  id: string;
  source_id: string;
  source_kind: CourseDesignAssemblySourceKind;
  source_name: string;
  locator: string;
  target_field: CourseDesignAssemblyTarget;
  mode: 'replace' | 'prepend' | 'append';
  content_preview: string;
  created_at: string;
}

export interface CourseDesignRecord {
  id: string;
  title: string;
  archive_id: string;
  chapter?: string | null;
  schedule_id?: string | null;
  primary_material_id: string;
  material_ids: string[];
  material_unit_id?: string | null;
  knowledge_outline_id?: string | null;
  knowledge_outline_version?: number | null;
  run_id?: string | null;
  status: CourseDesignStatus;
  version: number;
  template_document_id?: string | null;
  template_material_id?: string | null;
  source_snapshot?: {
    schedule: Record<string, unknown>[];
    syllabus_requirements: Record<string, unknown>[];
    knowledge_nodes: Record<string, unknown>[];
  };
  content_insertions: CourseDesignContentInsertion[];
  source_references: CourseDataReference[];
  exports: CourseDesignExportRecord[];
  content: CourseDesignContent;
  created_at: string;
  updated_at: string;
}

export interface CourseDesignSummary {
  id: string;
  title: string;
  archive_id: string;
  chapter?: string | null;
  run_id?: string | null;
  status: CourseDesignStatus;
  version: number;
  source_count: number;
  export_count: number;
  latest_export_at?: string | null;
  updated_at: string;
}

export interface CourseDesignTemplateInspection {
  template_mode: 'source-template' | 'standard-template';
  compatible: boolean;
  matched_fields: string[];
  unmatched_fields: string[];
  replacement_count: number;
  paragraph_count: number;
  table_count: number;
  header_count: number;
  footer_count: number;
  message: string;
}

export interface CourseDesignExportRecord {
  id: string;
  design_id: string;
  design_version: number;
  filename: string;
  document_id: string;
  template_mode: 'source-template' | 'standard-template';
  template_document_id?: string | null;
  template_material_id?: string | null;
  template_name: string;
  matched_fields: string[];
  sha256: string;
  size: number;
  preview_url: string;
  download_url: string;
  created_at: string;
}

export interface CourseReferenceDetail {
  reference: CourseDataReference;
  content: string;
  sections: DocumentSection[];
}

export type DataHubBlockKind = 'original' | 'extracted' | 'teaching_design' | 'student_question' | 'teacher_answer' | 'supervisor_review' | 'ideological_element' | 'imported';

export interface DataHubStats {
  terms: number;
  courses: number;
  units: number;
  materials: number;
  generated_blocks: number;
}

export interface DataHubUnit {
  id: string;
  archive_id: string;
  archive_name: string;
  academic_term: string;
  course_title: string;
  course_code: string;
  chapter: string;
  material_count: number;
  parsed_count: number;
  design_count: number;
  generated_count: number;
  updated_at: string;
}

export interface DataHubBlock {
  id: string;
  kind: DataHubBlockKind;
  title: string;
  content_preview: string;
  content: string;
  archive_id?: string | null;
  unit_id?: string | null;
  design_id?: string | null;
  run_id?: string | null;
  source_name: string;
  locator: string;
  original_url?: string | null;
  preview_url?: string | null;
  folder_id?: string | null;
  editable: boolean;
  updated_at: string;
  category?: string;
  modified_at?: number | string | null;
  source_folder_id?: string | null;
  source_kind?: 'upload' | 'local' | null;
  source_selection_kind?: 'files' | 'folder' | null;
  // S5: 解析状态/原文预览 (由 block_detail 补充)
  parse_status?: 'parsed' | 'metadata_only' | 'parse_failed' | 'unsupported' | null;
  extraction_engine?: string | null;
  text?: string | null;
}

export interface DataHubFolder {
  id: string;
  unit_id: string;
  name: string;
  parent_id?: string | null;
  system_parent?: DataHubBlockKind | null;
  created_at: string;
  updated_at: string;
  source_folder_id?: string | null;
  source_kind?: 'upload' | 'local' | null;
  source_selection_kind?: 'files' | 'folder' | null;
  source_path?: string | null;
  last_scanned_at?: string | null;
}

export interface DataHubLayout {
  unit_id: string;
  folders: DataHubFolder[];
  placements: Record<string, string>;
  titles: Record<string, string>;
  updated_at: string;
}

export type LocalSourceDiffStatus =
  | 'local_added'
  | 'local_removed'
  | 'local_changed'
  | 'platform_deleted'
  | 'local_directory_added'
  | 'platform_directory_added';

export interface LocalSourceDiffItem {
  path: string;
  kind: 'file' | 'directory';
  status: LocalSourceDiffStatus;
  local_size?: number | null;
  platform_size?: number | null;
  can_restore: boolean;
}

export interface LocalSourceDiffResult {
  archive_id: string;
  source_id: string;
  source_name: string;
  local_root: string;
  items: LocalSourceDiffItem[];
  local_changes: number;
  platform_changes: number;
  blocked_restores: number;
  checked_at: string;
}

export interface DataHubCatalog {
  stats: DataHubStats;
  terms: string[];
  courses: string[];
  units: DataHubUnit[];
  folders: DataHubFolder[];
  blocks: DataHubBlock[];
}

export interface LocalSourceScanResult {
  archive_id: string;
  archive_name: string;
  local_root: string;
  total_files: number;
  total_directories?: number;
  changes: { added: number; changed: number; unchanged: number; removed: number; parsed: number };
  warnings: string[];
  source_id: string;
  source_name: string;
  source_kind: 'local' | 'upload';
}

export interface SourceFolderResult {
  archive_id: string;
  source: ArchiveSourceFolder;
  changes: LocalSourceScanResult['changes'];
  total_files: number;
}

export interface ExternalOpenResult {
  opened: boolean;
  target: string;
  message: string;
}

export interface CompositionBlock {
  id: string;
  source_block_id?: string | null;
  kind: DataHubBlockKind;
  title: string;
  content: string;
  source_name: string;
  locator: string;
}

export interface CompositionRecord {
  id: string;
  title: string;
  archive_id?: string | null;
  unit_id?: string | null;
  blocks: CompositionBlock[];
  version: number;
  created_at: string;
  updated_at: string;
  import_document_id?: string | null;
  import_original_url?: string | null;
  import_preview_url?: string | null;
}

export interface CompositionSummary {
  id: string;
  title: string;
  archive_id?: string | null;
  unit_id?: string | null;
  version: number;
  block_count: number;
  updated_at: string;
}

export interface MaterialUnitFileAnalysis {
  material_id: string;
  name: string;
  path: string;
  category: string;
  extension: string;
  document_id?: string | null;
  preview_available: boolean;
  parse_status: 'parsed' | 'metadata_only' | 'parse_failed' | 'unsupported';
  parse_message: string;
  character_count: number;
  summary: string;
  section_count: number;
  knowledge_points: string[];
  extraction_engine: string;
  quality_level: string;
  archive_id?: string | null;
  source_unit_id?: string | null;
}

export interface MaterialUnitSummary {
  id: string;
  archive_id: string;
  archive_name: string;
  title: string;
  material_count: number;
  parsed_count: number;
  total_characters: number;
  overview: string;
  key_points: string[];
  created_at: string;
  updated_at: string;
  linked_unit_count: number;
  source_category_counts: Record<string, number>;
}

export interface MaterialUnitLink {
  unit_id: string;
  title: string;
  archive_id: string;
  archive_name: string;
  material_count: number;
  files: MaterialUnitFileAnalysis[];
}

export interface MaterialUnitRecord extends MaterialUnitSummary {
  material_ids: string[];
  files: MaterialUnitFileAnalysis[];
  linked_units: MaterialUnitLink[];
  material_references: MaterialUnitFileReference[];
  initial_outline?: MaterialUnitInitialOutline | null;
  scope_selection?: MaterialUnitScopeSelection;
  knowledge_outlines: MaterialUnitKnowledgeOutline[];
}

export interface MaterialUnitFileReference {
  id: string;
  source_unit_id: string;
  source_unit_title: string;
  archive_id: string;
  archive_name: string;
  material_id: string;
  file: MaterialUnitFileAnalysis;
}

export interface MaterialUnitScopeSelection {
  teaching_item_ids: string[];
  syllabus_item_ids: string[];
  outline_node_ids: string[];
}

export interface MaterialUnitScopeOption {
  id: string;
  title: string;
  content: string;
  source_material_id: string;
  source_unit_id: string;
  source_name: string;
  document_id?: string | null;
  source_hash?: string | null;
  locator: string;
}

export interface MaterialUnitOutlineNode {
  id: string;
  title: string;
  level: number;
  preview: string;
  source_material_id: string;
  source_unit_id: string;
  source_name: string;
  document_id?: string | null;
  source_hash?: string | null;
  locator: string;
}

export interface MaterialUnitScopeOptions {
  unit_id: string;
  course_title: string;
  teaching_items: MaterialUnitScopeOption[];
  syllabus_items: MaterialUnitScopeOption[];
  textbook_outline: MaterialUnitOutlineNode[];
}

export interface MaterialUnitInitialOutline {
  title: string;
  session: string;
  objective: string;
  scope_summary: string;
  sections: string[];
}

export type SyllabusRequirementType = 'objective' | 'knowledge' | 'key_point' | 'difficult_point' | 'practice' | 'assessment';

export interface MaterialUnitEvidence {
  id?: string;
  source_type: 'schedule' | 'syllabus' | 'textbook' | 'material' | 'teacher';
  material_id?: string;
  source_unit_id?: string;
  document_id?: string | null;
  source_hash?: string | null;
  locator: string;
  quote: string;
  label: string;
}

export interface MaterialUnitSyllabusMatch {
  id: string;
  category: SyllabusRequirementType;
  category_label: string;
  title: string;
  content: string;
  score: number;
  reason: string;
  recommended: boolean;
  evidence: MaterialUnitEvidence;
  custom?: boolean;  // 教师自定义/补充条目(非大纲原文)
}

export interface MaterialUnitScopeAlignment {
  unit_id: string;
  teaching_items: MaterialUnitScopeOption[];
  matches: MaterialUnitSyllabusMatch[];
  total_candidates: number;
  matching_method: 'deterministic' | 'hybrid';
  model_used: boolean;
}

export interface MaterialUnitKnowledgeNode {
  id: string;
  parent_id?: string | null;
  level: number;
  title: string;
  description: string;
  is_key_point: boolean;
  is_difficult_point: boolean;
  teacher_note: string;
  evidence: MaterialUnitEvidence[];
}

export interface MaterialUnitKnowledgeOutline {
  id: string;
  version: number;
  unit_id: string;
  status: 'draft' | 'confirmed';
  title: string;
  selected_session_ids: string[];
  selected_syllabus_item_ids: string[];
  selected_textbook_node_ids: string[];
  requirements: MaterialUnitSyllabusMatch[];
  nodes: MaterialUnitKnowledgeNode[];
  source_material_ids: string[];
  teacher_instruction: string;
  change_summary: string;
  based_on_version?: number | null;
  created_at: string;
  updated_at: string;
}

export type MaterialUnitRefineTaskStatus = 'queued' | 'loading_sources' | 'analyzing' | 'generating' | 'saving' | 'completed' | 'failed';

export interface MaterialUnitRefineTask {
  id: string;
  unit_id: string;
  outline_id: string;
  base_version: number;
  status: MaterialUnitRefineTaskStatus;
  stage_label: string;
  progress: number;
  material_ids: string[];
  teacher_instruction: string;
  use_model: boolean;
  result_version?: number | null;
  error: string;
  created_at: string;
  started_at?: string | null;
  updated_at: string;
  finished_at?: string | null;
  elapsed_seconds: number;
}

export interface ModelSettings {
  provider: 'mock' | 'openai_compatible' | 'dsh';
  base_url: string;
  model: string;
  temperature: number;
  timeout_seconds: number;
  has_api_key: boolean;
}

export interface ModelSettingsInput extends Omit<ModelSettings, 'has_api_key'> {
  api_key: string;
}

export interface ModelTestResult {
  ok: boolean;
  provider: string;
  model: string;
  latency_ms: number;
  message: string;
}

export interface ModelHistoryItem {
  provider: 'mock' | 'openai_compatible' | 'dsh';
  base_url: string;
  model: string;
  has_api_key: boolean;
  last_used_at: string;
  use_count: number;
}

export interface ModelDiscoveryResult {
  ok: boolean;
  provider: string;
  base_url: string;
  models: string[];
  latency_ms: number;
  message: string;
}

export type TeacherDraftStatus = 'draft' | 'reviewed';

export interface TeacherDraft {
  run_id: string;
  version: number;
  content: string;
  status: TeacherDraftStatus;
  source: 'generated' | 'teacher';
  updated_at: string;
}

export interface TeacherDraftVersion {
  version: number;
  content: string;
  status: TeacherDraftStatus;
  created_at: string;
}

export interface TeacherSectionGeneration {
  section_title: string;
  content: string;
}
