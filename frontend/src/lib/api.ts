import type {
  CreateRunInput,
  CourseArchiveDetail,
  CourseArchiveSummary,
  CompositionBlock,
  CompositionRecord,
  CompositionSummary,
  CourseDesignContent,
  CourseDesignAssemblySource,
  CourseDesignAssemblyTarget,
  CourseDesignExportRecord,
  CourseDesignRecord,
  CourseDesignStatus,
  CourseDesignSummary,
  CourseDesignTemplateInspection,
  CourseReferenceDetail,
  DataHubBlock,
  DataHubCatalog,
  DataHubLayout,
  DocumentVisualAnalysis,
  DocumentVisualAnalysisRequest,
  ModelSettings,
  ModelSettingsInput,
  ModelDiscoveryResult,
  ModelHistoryItem,
  LocalSourceScanResult,
  LocalSourceDiffResult,
  SourceFolderResult,
  ExternalOpenResult,
  ModelTestResult,
  ParsedDocument,
  PreparationPack,
  PrepareArchiveInput,
  ResumeInput,
  RunEvent,
  TeacherDraft,
  TeacherDraftStatus,
  TeacherDraftVersion,
  TeacherSectionGeneration,
  WorkflowRun,
  WorkflowTemplate,
} from '../types/workflow';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly body: { detail?: string; title?: string; errors?: Array<{ loc?: Array<string | number>; msg?: string }> } | null) {
    const validation = body?.errors?.[0];
    const field = validation?.loc?.filter((item) => item !== 'body').join('.') || '';
    const message = validation?.msg ? `${field ? `字段 ${field}：` : ''}${validation.msg}` : '';
    super(message || body?.detail || `API request failed (${status})`);
  }
}

export class NetworkRequestError extends Error {}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (reason) {
    if (reason instanceof TypeError) throw new NetworkRequestError('请求在到达后端前中断。上传大文件夹时请保留页面并重试，平台会按小批次继续处理。');
    throw reason;
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiError['body'];
    throw new ApiError(response.status, body);
  }
  // 204 无响应体，直接解析会抛异常
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const workflowApi = {
  listTemplates: () => request<WorkflowTemplate[]>('/workflows/templates'),
  listRuns: () => request<{ items: WorkflowRun[] }>('/workflows/runs'),
  getRun: (runId: string) => request<WorkflowRun>(`/workflows/runs/${runId}`),
  getEvents: (runId: string) => request<{ items: RunEvent[] }>(`/workflows/runs/${runId}/events`),
  createRun: (input: CreateRunInput) => request<WorkflowRun>('/workflows/runs', { method: 'POST', body: JSON.stringify(input) }),
  cancelRun: (runId: string) => request<WorkflowRun>(`/workflows/runs/${runId}/cancel`, { method: 'POST' }),
  resumeRun: (runId: string, input: ResumeInput) =>
    request<WorkflowRun>(`/workflows/runs/${runId}/resume`, { method: 'POST', body: JSON.stringify(input) }),
  continueRun: (runId: string, additional_iterations = 1, context = '') =>
    request<WorkflowRun>(`/workflows/runs/${runId}/continue`, { method: 'POST', body: JSON.stringify({ additional_iterations, context }) }),
  getTeacherDraft: (runId: string) =>
    request<TeacherDraft>(`/workflows/runs/${runId}/teacher-draft`),
  saveTeacherDraft: (runId: string, content: string, status: TeacherDraftStatus, base_version: number) =>
    request<TeacherDraft>(`/workflows/runs/${runId}/teacher-draft`, {
      method: 'PUT', body: JSON.stringify({ content, status, base_version }),
    }),
  listTeacherDraftVersions: (runId: string) =>
    request<{ items: TeacherDraftVersion[] }>(`/workflows/runs/${runId}/teacher-draft/versions`),
  generateTeacherSection: (runId: string, section_title: string, current_content: string, instruction: string) =>
    request<TeacherSectionGeneration>(`/workflows/runs/${runId}/teacher-draft/generations`, {
      method: 'POST', body: JSON.stringify({ section_title, current_content, instruction }),
    }),
  reportUrl: (runId: string, format: 'md' | 'pdf', variant: 'teacher' | 'student' = 'teacher') => `${API_BASE}/workflows/runs/${runId}/report.${format}?variant=${variant}`,
  deleteRun: (runId: string) => request<void>(`/workflows/runs/${runId}`, { method: 'DELETE' }),
};

export const documentApi = {
  parse: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<ParsedDocument>('/documents/parse', { method: 'POST', body });
  },
  previewUrl: (documentId: string) => `${API_BASE}/documents/${documentId}/preview`,
  originalUrl: (documentId: string) => `${API_BASE}/documents/${documentId}/original`,
  visualAnalyses: (documentId: string) =>
    request<{ items: DocumentVisualAnalysis[] }>(`/documents/${documentId}/visual-analyses`),
  analyzePage: (documentId: string, input: DocumentVisualAnalysisRequest) =>
    request<DocumentVisualAnalysis>(`/documents/${documentId}/visual-analysis`, {
      method: 'POST', body: JSON.stringify(input),
    }),
};

export const courseArchiveApi = {
  list: () => request<{ items: CourseArchiveSummary[] }>('/course-archives'),
  get: (archiveId: string) => request<CourseArchiveDetail>(`/course-archives/${archiveId}`),
  analyze: (archiveName: string, allFiles: File[], contentFiles: File[]) => {
    const body = new FormData();
    const manifest = allFiles.map((file) => ({
      path: file.webkitRelativePath || file.name,
      size: file.size,
      last_modified: file.lastModified,
    }));
    body.append('archive_name', archiveName);
    body.append('manifest', JSON.stringify(manifest));
    contentFiles.forEach((file) => body.append('files', file, file.webkitRelativePath || file.name));
    return request<CourseArchiveDetail>('/course-archives/analyze', { method: 'POST', body });
  },
  prepare: (archiveId: string, input: PrepareArchiveInput) =>
    request<PreparationPack>(`/course-archives/${archiveId}/prepare`, { method: 'POST', body: JSON.stringify(input) }),
  extract: (archiveId: string, materialIds: string[]) =>
    request<CourseArchiveDetail>(`/course-archives/${archiveId}/extract`, { method: 'POST', body: JSON.stringify({ material_ids: materialIds }) }),
  deletionImpact: (archiveId: string) =>
    request<import('../types/workflow').ArchiveDeletionImpact>(`/course-archives/${archiveId}/deletion-impact`),
  delete: (archiveId: string) =>
    request<import('../types/workflow').ArchiveDeletionResult>(`/course-archives/${archiveId}`, { method: 'DELETE' }),
};

export const courseDesignApi = {
  list: () => request<{ items: CourseDesignSummary[] }>('/course-designs'),
  get: (designId: string) => request<CourseDesignRecord>(`/course-designs/${designId}`),
  create: (input: PrepareArchiveInput & { archive_id: string; material_unit_id?: string; knowledge_outline_id?: string; knowledge_outline_version?: number }) =>
    request<CourseDesignRecord>('/course-designs', { method: 'POST', body: JSON.stringify(input) }),
  update: (designId: string, content: CourseDesignContent, status: CourseDesignStatus, base_version: number, template_document_id?: string | null, template_material_id?: string | null) =>
    request<CourseDesignRecord>(`/course-designs/${designId}`, {
      method: 'PUT', body: JSON.stringify({ content, status, base_version, template_document_id, template_material_id }),
    }),
  syncRun: (designId: string, runId: string) =>
    request<CourseDesignRecord>(`/course-designs/${designId}/sync-run/${runId}`, { method: 'POST' }),
  assemblySources: (designId: string, runId?: string) =>
    request<{ design_id: string; run_id?: string | null; items: CourseDesignAssemblySource[] }>(`/course-designs/${designId}/assembly-sources${runId ? `?run_id=${encodeURIComponent(runId)}` : ''}`),
  applyAssembly: (designId: string, input: { base_version: number; source_ids: string[]; target_field: CourseDesignAssemblyTarget; mode: 'replace' | 'prepend' | 'append'; custom_content?: string; custom_title?: string }, runId?: string) =>
    request<CourseDesignRecord>(`/course-designs/${designId}/assembly/apply${runId ? `?run_id=${encodeURIComponent(runId)}` : ''}`, { method: 'POST', body: JSON.stringify(input) }),
  source: (designId: string, referenceId: string) =>
    request<CourseReferenceDetail>(`/course-designs/${designId}/references/${referenceId}`),
  delete: (designId: string) => request<void>(`/course-designs/${designId}`, { method: 'DELETE' }),
  inspectTemplate: (designId: string, input: { template_material_id?: string | null; template_document_id?: string | null }) =>
    request<CourseDesignTemplateInspection>(`/course-designs/${designId}/template-inspection`, { method: 'POST', body: JSON.stringify(input) }),
  exports: (designId: string) => request<{ items: CourseDesignExportRecord[] }>(`/course-designs/${designId}/exports`),
  deleteExport: (designId: string, exportId: string) => request<void>(`/course-designs/${designId}/exports/${exportId}`, { method: 'DELETE' }),
  exportDocx: async (designId: string, input: { template_material_id?: string | null; template_document_id?: string | null; filename?: string; preserve_source_format?: boolean }) => {
    const response = await fetch(`${API_BASE}/course-designs/${designId}/export.docx`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as ApiError['body'];
      throw new ApiError(response.status, body);
    }
    return {
      blob: await response.blob(),
      disposition: response.headers.get('Content-Disposition') || '',
      templateMode: response.headers.get('X-Template-Mode') || '',
      exportId: response.headers.get('X-Export-ID') || '',
      documentId: response.headers.get('X-Document-ID') || '',
    };
  },
};

export const materialUnitApi = {
  list: (archiveId = '') => request<{ items: import('../types/workflow').MaterialUnitSummary[] }>(`/material-units${archiveId ? `?archive_id=${encodeURIComponent(archiveId)}` : ''}`),
  get: (unitId: string) => request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}`),
  create: (input: { archive_id: string; title: string; material_ids: string[] }) =>
    request<import('../types/workflow').MaterialUnitRecord>('/material-units', { method: 'POST', body: JSON.stringify(input) }),
  append: (unitId: string, materialIds: string[]) =>
    request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}/materials`, { method: 'POST', body: JSON.stringify({ material_ids: materialIds }) }),
  rename: (unitId: string, title: string) =>
    request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  remove: (unitId: string) => request<void>(`/material-units/${unitId}`, { method: 'DELETE' }),
  reference: (unitId: string, unitIds: string[]) =>
    request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}/references`, { method: 'POST', body: JSON.stringify({ unit_ids: unitIds }) }),
  referenceMaterials: (unitId: string, sourceUnitId: string, materialIds: string[]) =>
    request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}/material-references`, { method: 'POST', body: JSON.stringify({ source_unit_id: sourceUnitId, material_ids: materialIds }) }),
  removeMaterialReference: (unitId: string, referenceId: string) =>
    request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}/material-references/${referenceId}`, { method: 'DELETE' }),
  merge: (unitId: string, sourceUnitIds: string[], title?: string) =>    request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}/merge`, { method: 'POST', body: JSON.stringify({ source_unit_ids: sourceUnitIds, title: title || null }) }),
  parseTask: (unitId: string, materialIds: string[]) =>
    request<{ task_id: string; status: string }>(`/material-units/${unitId}/parse-tasks`, { method: 'POST', body: JSON.stringify({ material_ids: materialIds }) }),
  parseTaskStatus: (unitId: string, taskId: string) =>
    request<{ task_id: string; status: string; progress: number; engine: string; materials: Array<{ id: string; name: string; status: string; progress: number; message: string }> }>(`/material-units/${unitId}/parse-tasks/${taskId}`),
  fileText: (unitId: string, materialId: string) =>
    request<{ ok: boolean; material_id: string; character_count: number; text: string; pages?: Array<{ page: number; text: string }> }>(`/material-units/${unitId}/files/${materialId}/text`),
  reparseFile: (unitId: string, materialId: string, engine: string) =>
    request<{ task_id: string; status: string; engine: string }>(`/material-units/${unitId}/files/${materialId}/reparse`, { method: 'POST', body: JSON.stringify({ engine }) }),
  scopeOptions: (unitId: string) => request<import('../types/workflow').MaterialUnitScopeOptions>(`/material-units/${unitId}/scope-options`),
  syllabusMatches: (unitId: string, teachingItemIds: string[], useModel = true) =>
    request<import('../types/workflow').MaterialUnitScopeAlignment>(`/material-units/${unitId}/syllabus-matches`, { method: 'POST', body: JSON.stringify({ teaching_item_ids: teachingItemIds, use_model: useModel, limit_per_category: 4 }) }),
  listKnowledgeOutlines: (unitId: string, includeVersions = false) =>
    request<{ items: import('../types/workflow').MaterialUnitKnowledgeOutline[] }>(`/material-units/${unitId}/knowledge-outlines${includeVersions ? '?include_versions=true' : ''}`),
  createKnowledgeOutline: (unitId: string, input: { title?: string; teaching_item_ids: string[]; syllabus_item_ids: string[]; outline_node_ids: string[]; status?: 'draft' | 'confirmed'; teacher_instruction?: string }) =>
    request<import('../types/workflow').MaterialUnitKnowledgeOutline>(`/material-units/${unitId}/knowledge-outlines`, { method: 'POST', body: JSON.stringify(input) }),
  synthesizeOutline: (unitId: string, input: { teaching_item_ids: string[]; syllabus_item_ids: string[]; outline_node_ids: string[]; teacher_instruction?: string; title?: string }) =>
    request<import('../types/workflow').MaterialUnitKnowledgeOutline>(`/material-units/${unitId}/knowledge-outlines/synthesize`, { method: 'POST', body: JSON.stringify(input) }),
  updateKnowledgeOutline: (unitId: string, outlineId: string, input: { base_version: number; title?: string; status?: 'draft' | 'confirmed'; nodes?: import('../types/workflow').MaterialUnitKnowledgeNode[]; teacher_instruction?: string; change_summary?: string }) =>
    request<import('../types/workflow').MaterialUnitKnowledgeOutline>(`/material-units/${unitId}/knowledge-outlines/${outlineId}`, { method: 'PUT', body: JSON.stringify(input) }),
  deleteKnowledgeOutline: (unitId: string, outlineId: string, version: number, allHistory = false) =>
    request<void>(`/material-units/${unitId}/knowledge-outlines/${outlineId}?version=${version}&all_history=${allHistory}`, { method: 'DELETE' }),
  createRefineTask: (unitId: string, outlineId: string, input: { material_ids: string[]; teacher_instruction: string; base_version?: number; use_model?: boolean }) =>
    request<import('../types/workflow').MaterialUnitRefineTask>(`/material-units/${unitId}/knowledge-outlines/${outlineId}/refine-tasks`, { method: 'POST', body: JSON.stringify(input) }),
  listRefineTasks: (unitId: string, outlineId: string) =>
    request<{ items: import('../types/workflow').MaterialUnitRefineTask[] }>(`/material-units/${unitId}/knowledge-outlines/${outlineId}/refine-tasks`),
  getRefineTask: (unitId: string, outlineId: string, taskId: string) =>
    request<import('../types/workflow').MaterialUnitRefineTask>(`/material-units/${unitId}/knowledge-outlines/${outlineId}/refine-tasks/${taskId}`),
  refineKnowledgeOutline: (unitId: string, outlineId: string, input: { material_ids: string[]; teacher_instruction: string; base_version?: number; use_model?: boolean }) =>
    request<import('../types/workflow').MaterialUnitKnowledgeOutline>(`/material-units/${unitId}/knowledge-outlines/${outlineId}/refine`, { method: 'POST', body: JSON.stringify(input) }),
  graphChat: (unitId: string, input: { material_id: string; question: string; quote?: string; chat_id?: string; context_node_id?: string }) =>
    request<{ chat_id: string; answer: string; question: string; quote: string; section_title?: string }>(`/material-units/${unitId}/graph-chat`, { method: 'POST', body: JSON.stringify(input) }),
  graphChats: (unitId: string, materialId?: string) =>
    request<{ items: Array<{ id: string; material_id: string; quote: string; question: string; rounds: Array<{ role: string; content: string }>; context_node_id?: string; section_title?: string; saved_node_id: string | null; updated_at: string }> }>(`/material-units/${unitId}/graph-chats${materialId ? `?material_id=${materialId}` : ''}`),
  graphChatClear: (unitId: string, chatId: string) =>
    request<{ ok: boolean }>(`/material-units/${unitId}/graph-chats/${chatId}/clear`, { method: 'POST', body: '{}' }),
  graphChatSave: (unitId: string, chatId: string, title?: string, parentId?: string) =>
    request<{ ok: boolean; node_id: string; title: string; md_file: string; content: string }>(`/material-units/${unitId}/graph-chats/${chatId}/save`, { method: 'POST', body: JSON.stringify({ title: title || '', parent_id: parentId || '' }) }),
  graphNodes: (unitId: string, materialId?: string) =>
    request<{ items: Array<{ id: string; material_id: string; title: string; quote: string; md_file: string; content: string; updated_at: string; parent_id?: string | null; section_title?: string }> }>(`/material-units/${unitId}/graph-nodes${materialId ? `?material_id=${materialId}` : ''}`),
  graphNodeInsertOutline: (unitId: string, nodeId: string, input: { outline_id: string; node_id: string }) =>
    request<{ ok: boolean; title: string; duplicate?: boolean }>(`/material-units/${unitId}/graph-nodes/${nodeId}/insert-outline`, { method: 'POST', body: JSON.stringify(input) }),
  graphNodeUnlinkOutline: (unitId: string, nodeId: string, input: { outline_id: string; node_id: string }) =>
    request<{ ok: boolean }>(`/material-units/${unitId}/graph-nodes/${nodeId}/unlink-outline`, { method: 'POST', body: JSON.stringify(input) }),
  graphNodeOutlineImports: (unitId: string, nodeId: string) =>
    request<{ items: Array<{ outline_id: string; outline_version: number; outline_title: string; node_id: string; node_title: string; quote: string }> }>(`/material-units/${unitId}/graph-nodes/${nodeId}/outline-imports`),
  graphNodeDelete: (unitId: string, nodeId: string) =>
    request<{ ok: boolean }>(`/material-units/${unitId}/graph-nodes/${nodeId}`, { method: 'DELETE' }),
  initialOutline: (unitId: string, input: { teaching_item_ids: string[]; syllabus_item_ids: string[]; outline_node_ids: string[]; title?: string }) =>
    request<import('../types/workflow').MaterialUnitInitialOutline>(`/material-units/${unitId}/initial-outline`, { method: 'POST', body: JSON.stringify(input) }),
  saveInitialOutline: (unitId: string, outline: import('../types/workflow').MaterialUnitInitialOutline, scopeSelection: import('../types/workflow').MaterialUnitScopeSelection) =>
    request<import('../types/workflow').MaterialUnitRecord>(`/material-units/${unitId}/initial-outline`, { method: 'PUT', body: JSON.stringify({ outline, scope_selection: scopeSelection }) }),
};

export const dataHubApi = {
  catalog: (filters: { q?: string; term?: string; course?: string; kind?: string; summary_only?: boolean; unit_id?: string } = {}) => {
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value).map(([key, value]) => [key, String(value)]));
    return request<DataHubCatalog>(`/data-hub/catalog${query.size ? `?${query}` : ''}`);
  },
  block: (blockId: string) => request<DataHubBlock>(`/data-hub/blocks/${encodeURIComponent(blockId)}`),
  createLibraryRoot: (name: string) =>
    request<CourseArchiveDetail>('/data-hub/library-roots', { method: 'POST', body: JSON.stringify({ name }) }),
  renameLibraryRoot: (archiveId: string, name: string) =>
    request<CourseArchiveDetail>(`/data-hub/library-roots/${archiveId}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  createFolder: (input: { unit_id: string; name: string; parent_id?: string | null; system_parent?: DataHubBlock['kind'] | null }) =>
    request<DataHubLayout>('/data-hub/folders', { method: 'POST', body: JSON.stringify(input) }),
  updateFolder: (folderId: string, input: { name?: string; move?: boolean; parent_id?: string | null; system_parent?: DataHubBlock['kind'] | null }) =>
    request<DataHubLayout>(`/data-hub/folders/${folderId}`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteFolder: (folderId: string, recursive = false) => request<void>(`/data-hub/folders/${folderId}${recursive ? '?recursive=true' : ''}`, { method: 'DELETE' }),
  updateBlock: (blockId: string, input: { unit_id: string; title?: string; move?: boolean; folder_id?: string | null }) =>
    request<DataHubLayout>(`/data-hub/blocks/${encodeURIComponent(blockId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  moveBlocks: (input: { unit_id: string; block_ids: string[]; folder_id?: string | null }) =>
    request<DataHubLayout>('/data-hub/blocks/move', { method: 'POST', body: JSON.stringify(input) }),
  transferLocalMaterials: (input: { unit_id: string; block_ids: string[]; destination_folder_id: string; operation: 'copy' | 'move' }) =>
    request<LocalSourceScanResult>('/data-hub/materials/local-transfer', { method: 'POST', body: JSON.stringify(input) }),
  syncFolderToLocal: (input: { unit_id: string; folder_id: string }) =>
    request<{ archive_id: string; unit_id: string; source_id: string; synced_files: number; created_directories: number; message: string }>('/data-hub/local-sync/folder', { method: 'POST', body: JSON.stringify(input) }),
  syncUploadsToLocal: (input: { unit_id: string; folder_id: string; browser_source_id: string; root_name: string; directories: string[]; files: File[] }) => {
    const body = new FormData();
    body.append('unit_id', input.unit_id);
    body.append('folder_id', input.folder_id);
    body.append('browser_source_id', input.browser_source_id);
    body.append('root_name', input.root_name);
    body.append('directories', JSON.stringify(input.directories));
    input.files.forEach((file) => {
      const parts = (file.webkitRelativePath || file.name).replace(/\\/g, '/').split('/').filter(Boolean);
      const relative = input.root_name && parts[0] === input.root_name ? parts.slice(1).join('/') : parts.join('/');
      body.append('files', file, relative || file.name);
    });
    return request<{ archive_id: string; unit_id: string; source_id: string; synced_files: number; created_directories: number; message: string }>('/data-hub/local-sync/uploads', { method: 'POST', body });
  },
  uploadFiles: (input: { unit_id: string; folder_id?: string | null; destination_path: string[]; files: File[] }) => {
    const body = new FormData();
    body.append('unit_id', input.unit_id);
    body.append('folder_id', input.folder_id || '');
    body.append('destination_path', JSON.stringify(input.destination_path));
    input.files.forEach((file) => body.append('files', file, file.webkitRelativePath || file.name));
    return request<{ archive_id: string; unit_id: string; material_count: number; folder_count: number }>('/data-hub/uploads', { method: 'POST', body });
  },
  deleteBlock: (blockId: string, unitId: string) =>
    request<void>(`/data-hub/blocks/${encodeURIComponent(blockId)}?unit_id=${encodeURIComponent(unitId)}`, { method: 'DELETE' }),
  deleteBlocks: (input: { unit_id: string; block_ids: string[] }) =>
    request<void>('/data-hub/blocks/delete', { method: 'POST', body: JSON.stringify(input) }),
  organizeImport: (archiveId: string, folderName: string) =>
    request<{ archive_id: string; unit_count: number; folder_count: number; block_count: number }>(`/data-hub/archives/${archiveId}/import-folder`, { method: 'POST', body: JSON.stringify({ folder_name: folderName }) }),
  updateArchiveMetadata: (archiveId: string, input: { academic_term: string; course_title: string; course_code: string }) =>
    request<CourseArchiveDetail>(`/data-hub/archives/${archiveId}/metadata`, { method: 'PUT', body: JSON.stringify(input) }),
  renameAcademicTerm: (input: { current_name: string; new_name: string }) =>
    request<{ previous_name: string; academic_term: string; updated_courses: number }>('/data-hub/academic-terms/rename', { method: 'PUT', body: JSON.stringify(input) }),
  scanLocal: (input: { root_path: string; archive_id?: string | null; archive_name?: string; academic_term?: string; course_title?: string; course_code?: string; source_id?: string | null; source_name?: string }) =>
    request<LocalSourceScanResult>('/data-hub/local-sources/scan', { method: 'POST', body: JSON.stringify(input) }),
  registerBrowserSource: (input: { archive_id?: string | null; source_id?: string | null; source_name: string; academic_term?: string; course_title?: string; course_code?: string; selection_kind: 'files' | 'folder'; manifest: Array<{ path: string; size: number; last_modified?: number }>; directories?: string[]; parent_folder_id?: string | null }) =>
    request<SourceFolderResult>('/data-hub/sources/browser', { method: 'POST', body: JSON.stringify(input) }),
  uploadSourceFiles: (archiveId: string, sourceId: string, files: Array<{ file: File; path: string }>) => {
    const body = new FormData();
    files.forEach(({ file, path }) => body.append('files', file, path));
    return request<{ archive_id: string; source_id: string; uploaded: number; total_files: number }>(`/data-hub/archives/${archiveId}/sources/${sourceId}/files`, { method: 'POST', body });
  },
  organizeSource: (archiveId: string, sourceId: string) =>
    request<{ archive_id: string; source_id: string; unit_count: number; folder_count: number; block_count: number }>(`/data-hub/archives/${archiveId}/sources/${sourceId}/organize`, { method: 'POST' }),
  refreshSource: (archiveId: string, sourceId: string) =>
    request<LocalSourceScanResult>(`/data-hub/archives/${archiveId}/sources/${sourceId}/refresh`, { method: 'POST' }),
  sourceDiff: (archiveId: string, sourceId: string) =>
    request<LocalSourceDiffResult>(`/data-hub/archives/${archiveId}/sources/${sourceId}/diff`),
  reconcileSource: (archiveId: string, sourceId: string, direction: 'update_platform' | 'update_local') =>
    request<{ archive_id: string; source_id: string; direction: 'update_platform' | 'update_local'; applied: number; skipped: number; message: string }>(`/data-hub/archives/${archiveId}/sources/${sourceId}/reconcile`, { method: 'POST', body: JSON.stringify({ direction }) }),
  openSource: (archiveId: string, sourceId: string) =>
    request<ExternalOpenResult>(`/data-hub/archives/${archiveId}/sources/${sourceId}/open`, { method: 'POST' }),
  deleteSource: (archiveId: string, sourceId: string) =>
    request<void>(`/data-hub/archives/${archiveId}/sources/${sourceId}`, { method: 'DELETE' }),
  openMaterial: (archiveId: string, materialId: string) =>
    request<ExternalOpenResult>(`/data-hub/archives/${archiveId}/materials/${materialId}/open`, { method: 'POST' }),
  reloadMaterial: (archiveId: string, materialId: string) =>
    request<{ archive_id: string; material_id: string; reloaded: boolean; updated_at: string }>(`/data-hub/archives/${archiveId}/materials/${materialId}/reload`, { method: 'POST' }),
  listCompositions: () => request<{ items: CompositionSummary[] }>('/data-hub/compositions'),
  getComposition: (id: string) => request<CompositionRecord>(`/data-hub/compositions/${id}`),
  createComposition: (input: { title: string; archive_id?: string | null; unit_id?: string | null; blocks: CompositionBlock[] }) =>
    request<CompositionRecord>('/data-hub/compositions', { method: 'POST', body: JSON.stringify(input) }),
  updateComposition: (record: CompositionRecord) => request<CompositionRecord>(`/data-hub/compositions/${record.id}`, {
    method: 'PUT', body: JSON.stringify({ title: record.title, archive_id: record.archive_id, unit_id: record.unit_id, blocks: record.blocks, base_version: record.version }),
  }),
  importComposition: (file: File) => {
    const body = new FormData(); body.append('file', file);
    return request<CompositionRecord>('/data-hub/compositions/import', { method: 'POST', body });
  },
  deleteComposition: (id: string) => request<void>(`/data-hub/compositions/${id}`, { method: 'DELETE' }),
  previewUrl: (id: string) => `${API_BASE}/data-hub/compositions/${id}/preview`,
  exportUrl: (id: string, format: 'docx' | 'md' | 'json') => `${API_BASE}/data-hub/compositions/${id}/export?format=${format}`,
};

export const modelSettingsApi = {
  get: () => request<ModelSettings>('/settings/model'),
  update: (input: ModelSettingsInput) => request<ModelSettings>('/settings/model', { method: 'PUT', body: JSON.stringify(input) }),
  test: (input: ModelSettingsInput) => request<ModelTestResult>('/settings/model/test', { method: 'POST', body: JSON.stringify(input) }),
  history: () => request<ModelHistoryItem[]>('/settings/model/history'),
  discover: (input: ModelSettingsInput) => request<ModelDiscoveryResult>('/settings/model/discover', { method: 'POST', body: JSON.stringify(input) }),
};

export function workflowEventsUrl(runId: string): string {
  const explicit = import.meta.env.VITE_WS_BASE_URL as string | undefined;
  const origin = explicit ? explicit.replace(/\/$/, '') : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
  return `${origin}${API_BASE}/workflows/runs/${runId}/events/ws`;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof NetworkRequestError) return error.message;
  if (error instanceof TypeError) return '网络请求未完成，请刷新页面后重试。';
  if (error instanceof Error) return error.message;
  return '发生未知错误，请稍后重试。';
}
