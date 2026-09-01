import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle, BookOpen, CheckCircle2, ChevronDown, Copy, StopCircle, Clock3,
  FileCheck2, FileDown, FileText, FolderOpen, Hand, Layers3, Link2, ListChecks, Loader2, MessageCircleQuestion, Play, Plus,
  PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Radio, RefreshCw, Repeat, ScanSearch, Send, ShieldCheck, Upload, X,
} from 'lucide-react';
import { ModelSettingsPanel } from './components/ModelSettingsPanel';
import { KnowledgePointEditor } from './components/KnowledgePointEditor';
import { TeachingScopePlanner } from './components/TeachingScopePlanner';
import { SessionRunCard } from './components/SessionRunCard';
import { TeachingProgress } from './components/TeachingProgress';
import { TeacherMaterialsWorkspace } from './components/TeacherMaterialsWorkspace';
import { DocumentPreviewWorkspace } from './components/DocumentPreviewWorkspace';
import { GenerationStatusPanel } from './components/GenerationStatusPanel';
import { AgentFlowWorkspace } from './components/AgentFlowWorkspace';
import { CourseArchiveWorkspace } from './components/CourseArchiveWorkspace';
import { ExportWorkspace } from './components/ExportWorkspace';
import { DataHubWorkspace } from './components/DataHubWorkspace';
import { DataHubDashboard } from './components/DataHubDashboard';
import { MaterialUnitWorkspace } from './components/MaterialUnitWorkspace';
import { CompositionWorkspace } from './components/CompositionWorkspace';
import { ModelQuickSwitcher } from './components/ModelQuickSwitcher';
import { StageNavigation, type AppStage } from './components/StageNavigation';
import { WelcomePanel } from './components/WelcomePanel';
import { DEMO_COURSE } from './lib/demoCourse';
import { useWorkflowEvents } from './hooks/useWorkflowEvents';
import { courseArchiveApi, courseDesignApi, dataHubApi, documentApi, getErrorMessage, modelSettingsApi, workflowApi } from './lib/api';
import type { ArchiveDeletionResult, CourseArchiveDetail, CourseArchiveSummary, CourseDesignRecord, CourseDesignSummary, DataHubBlock, DocumentVisualAnalysis, InterventionPoint, KnowledgePoint, ModelSettings, ParsedDocument, PendingInput, PreparationPack, PrepareArchiveInput, ResumeInput, RunEvent, TeachingData, TeachingMessage, TeachingPhase, TeachingScope, WorkflowRun } from './types/workflow';

const phases: Array<{ key: string; phase: TeachingPhase; name: string; short: string }> = [
  { key: 'content_analysis', phase: 'design', name: '内容剖析', short: '重难点' },
  { key: 'teaching_design', phase: 'design', name: '教学设计', short: '目标与环节' },
  { key: 'teach_knowledge', phase: 'teach_knowledge', name: '教师讲授', short: '课堂实施' },
  { key: 'student_question', phase: 'student_question', name: '学生提问', short: '分层学习者' },
  { key: 'teacher_answer', phase: 'teacher_answer', name: '教师答疑', short: '澄清误区' },
  { key: 'supervisor_comment', phase: 'supervisor_comment', name: '督导点评', short: '评价改进' },
];
const terminalStatuses = new Set(['completed', 'failed', 'cancelled']);
const levelNames: Record<string, string> = { high: '拓展型', medium: '进阶型', low: '基础型' };
type WorkspaceView = 'material' | 'process' | 'result';
type ExportSubpage = 'compose' | 'lesson';
type MaterialSubpage = 'units' | 'preparation';

function stageFromPath(pathname: string): AppStage {
  if (pathname.startsWith('/overview')) return 'overview';
  if (pathname.startsWith('/hub')) return 'hub';
  if (pathname.startsWith('/materials')) return 'materials';
  if (pathname.startsWith('/exports')) return 'exports';
  if (pathname.startsWith('/design')) return 'design';
  return 'overview';
}

function exportSubpageFromPath(pathname: string): ExportSubpage {
  return pathname.startsWith('/exports/lesson') ? 'lesson' : 'compose';
}
function materialSubpageFromPath(pathname: string): MaterialSubpage {
  return pathname.startsWith('/materials/preparation') ? 'preparation' : 'units';
}

const stagePaths: Record<AppStage, string> = { overview: '/overview', hub: '/hub', materials: '/materials', design: '/design', exports: '/exports/compose' };

const archiveExcludedSegments = new Set(['node_modules', 'dist', 'build', '.git', '__pycache__', '.venv', 'venv', '.cache', '.claude', '.agents', '.trae', '.runtime']);

function archivePath(file: File): string { return file.webkitRelativePath || file.name; }
function relevantArchiveFiles(files: File[]): File[] {
  return files.filter((file) => !archivePath(file).split('/').slice(1).some((part) => part.startsWith('.') || archiveExcludedSegments.has(part.toLowerCase())));
}

function designSummary(design: CourseDesignRecord): CourseDesignSummary {
  const exports = design.exports || [];
  return {
    id: design.id,
    title: design.title,
    archive_id: design.archive_id,
    chapter: design.chapter,
    run_id: design.run_id,
    status: design.status,
    version: design.version,
    source_count: design.source_references.length,
    export_count: exports.length,
    latest_export_at: exports.length ? exports[exports.length - 1].created_at : null,
    updated_at: design.updated_at,
  };
}

function visualEvidenceContext(items: DocumentVisualAnalysis[]): string {
  if (!items.length) return '';
  const pages = items.map((item) => {
    const elements = item.visual_elements.map((element) => `${element.title}：${element.description}`).join('；');
    const corrections = item.ocr_corrections.map((correction) => `${correction.recognized || '漏字'}→${correction.corrected}`).join('；');
    const notes = item.teaching_notes.join('；');
    return [`第${item.page_number}页：${item.summary}`, elements && `视觉要素：${elements}`, corrections && `文字复核：${corrections}`, notes && `备课提示：${notes}`].filter(Boolean).join('\n');
  });
  return `教师已在原页预览中完成视觉复核。以下内容是对图表、公式、版式和 OCR 的补充证据，只作材料依据，不得覆盖与原文冲突的内容：\n${pages.join('\n\n')}`;
}

function statusLabel(status: WorkflowRun['status']) { return { queued: '正在启动', running: '教学进行中', paused: '等待你处理', completed: '已完成', failed: '运行失败', cancelled: '已停止' }[status]; }

function eventTeachingData(run: WorkflowRun | null, events: RunEvent[]): TeachingData {
  const base = run?.teaching_data || {};
  const messages = [...(base.messages || [])];
  const messageIds = new Set(messages.map((message) => message.id));
  const data: TeachingData = { ...base, messages };
  events.forEach((event) => {
    const payload = event.payload;
    if (payload.analysis) data.content_analysis = payload.analysis as TeachingData['content_analysis'];
    if (payload.knowledge_points) data.knowledge_points = payload.knowledge_points as TeachingData['knowledge_points'];
    if (payload.document_sections) data.document_sections = payload.document_sections as TeachingData['document_sections'];
    if (payload.framework) data.teaching_framework = payload.framework as TeachingData['teaching_framework'];
    if (payload.messages) {
      for (const message of payload.messages as TeachingMessage[]) {
        if (!messageIds.has(message.id)) {
          data.messages = [...(data.messages || []), message];
          messageIds.add(message.id);
        }
      }
    }
    if (typeof payload.iteration === 'number') data.current_iteration = payload.iteration;
  });
  return data;
}

/** 流程停在断点时的介入面板：教学设计评审与答疑分工两种形态 */
function InterventionPanel({ pending, value, onChange, busy, onSubmit }: {
  pending: PendingInput;
  value: string;
  onChange: (value: string) => void;
  busy: boolean;
  onSubmit: (action: ResumeInput['action']) => void;
}) {
  const design = pending.kind === 'design_review';
  const empty = value.trim().length === 0;
  return (
    <div className="intervene-card">
      <header>
        <Hand size={15} /><strong>{design ? '教学设计待确认' : '这一轮由谁来答疑'}</strong>
        {pending.iteration > 0 && <span className="round-tag">第 {pending.iteration} 轮</span>}
      </header>
      <p className="intervene-prompt">{pending.prompt}</p>
      {design && !!pending.context.stages?.length && (
        <ul className="intervene-stages">
          {pending.context.stages.map((stage) => <li key={stage.name}><strong>{stage.name}</strong><span>{stage.activity}</span><em>{stage.minutes} 分钟</em></li>)}
        </ul>
      )}
      {!design && !!pending.context.questions?.length && (
        <ul className="intervene-questions">
          {pending.context.questions.map((question, index) => (
            <li key={index}>
              <span className={`level level-${question.level || 'medium'}`}>{question.level ? levelNames[question.level] : '学生'}</span>
              <p>{question.content}</p>
            </li>
          ))}
        </ul>
      )}
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={3}
        placeholder={design ? '写下你对重难点或课堂环节的修改意见，例如：难点环节延长到 15 分钟，增加对比练习' : '写下完整答复，或只写要点交给教师扩写'}
      />
      <div className="intervene-actions">
        {design ? (
          <>
            <button type="button" className="primary-button" disabled={busy || empty} onClick={() => onSubmit('revise')} title={empty ? '请先写下修改意见' : '按我的意见重新设计'}>{busy ? <Loader2 className="spin" size={15} /> : <Send size={15} />}按我的意见调整</button>
            <button type="button" className="secondary-button" disabled={busy} onClick={() => onSubmit('continue')}>方案可以，开始上课</button>
          </>
        ) : (
          <>
            <button type="button" className="primary-button" disabled={busy || empty} onClick={() => onSubmit('user')} title={empty ? '请先写下答复内容' : '这段内容将作为本轮答疑'}>{busy ? <Loader2 className="spin" size={15} /> : <Send size={15} />}用我写的答复</button>
            <button type="button" className="secondary-button" disabled={busy || empty} onClick={() => onSubmit('outline')} title={empty ? '请先写下要点' : '教师按我的要点展开'}>按我的要点扩写</button>
            <button type="button" className="secondary-button" disabled={busy} onClick={() => onSubmit('agent')}>交给教师智能体</button>
          </>
        )}
      </div>
    </div>
  );
}

/** 按教学轮次切分消息，使"第几轮"和角色分工在视觉上一目了然 */
function groupByIteration(messages: TeachingMessage[]) {
  const groups: Array<{ iteration: number; items: TeachingMessage[] }> = [];
  messages.forEach((message) => {
    const existing = groups.find((group) => group.iteration === message.iteration);
    if (existing) existing.items.push(message);
    else groups.push({ iteration: message.iteration, items: [message] });
  });
  return groups;
}

function App() {
  const fileInput = useRef<HTMLInputElement>(null);
  const indexedSourceFiles = useRef<Map<string, File>>(new Map());
  const hydratedDesignId = useRef<string | null>(null);
  // 用户主动点击会话时置位, 让"activeDesign 未绑定 run 则清掉选择"的 effect 不误清用户的主动选择
  const userSelectedRunRef = useRef<string | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [parsedDoc, setParsedDoc] = useState<ParsedDocument | null>(null);
  const [title, setTitle] = useState('');
  const [context, setContext] = useState('');
  const [iterations, setIterations] = useState(2);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadElapsed, setUploadElapsed] = useState(0);
  const [uploadFileName, setUploadFileName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>('process');
  const [appStage, setAppStage] = useState<AppStage>(() => stageFromPath(window.location.pathname));
  const [projectPanelOpen, setProjectPanelOpen] = useState(true);
  const [detailPanelOpen, setDetailPanelOpen] = useState(false);
  const [messageView, setMessageView] = useState<'latest' | 'all' | number>('latest');
  const [modelLabel, setModelLabel] = useState('读取中');
  const [modelSettings, setModelSettings] = useState<ModelSettings | null>(null);
  const [modelRefreshKey, setModelRefreshKey] = useState(0);
  const [detailTab, setDetailTab] = useState<'analysis' | 'framework' | 'review'>('analysis');
  const [editedPoints, setEditedPoints] = useState<KnowledgePoint[]>([]);
  const [scope, setScope] = useState<TeachingScope>({ selected_point_titles: [], estimated_minutes: 45, depth: 'standard' });
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [interventions, setInterventions] = useState<InterventionPoint>({ after_design: false, after_question: false });
  const [visualEvidence, setVisualEvidence] = useState<DocumentVisualAnalysis[]>([]);
  const [resumeText, setResumeText] = useState('');
  const [resuming, setResuming] = useState(false);
  const [archives, setArchives] = useState<CourseArchiveSummary[]>([]);
  const [selectedArchive, setSelectedArchive] = useState<CourseArchiveDetail | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveImporting, setArchiveImporting] = useState(false);
  const [archivePreparing, setArchivePreparing] = useState(false);
  const [archiveElapsed, setArchiveElapsed] = useState(0);
  const [archiveImportCounts, setArchiveImportCounts] = useState({ total: 0, content: 0 });
  const [designs, setDesigns] = useState<CourseDesignSummary[]>([]);
  const [activeDesign, setActiveDesign] = useState<CourseDesignRecord | null>(null);
  const [designLoading, setDesignLoading] = useState(false);
  const [exportSubpage, setExportSubpage] = useState<ExportSubpage>(() => exportSubpageFromPath(window.location.pathname));
  const [materialSubpage, setMaterialSubpage] = useState<MaterialSubpage>(() => materialSubpageFromPath(window.location.pathname));
  const [materialUnitRefreshKey, setMaterialUnitRefreshKey] = useState(0);
  const [pendingHubBlocks, setPendingHubBlocks] = useState<DataHubBlock[]>([]);

  const navigateStage = useCallback((stage: AppStage, replace = false) => {
    if (stage === 'exports') setExportSubpage('compose');
    if (stage === 'materials') setMaterialSubpage('units');
    setAppStage(stage);
    const path = stagePaths[stage];
    if (window.location.pathname !== path) window.history[replace ? 'replaceState' : 'pushState']({ stage }, '', path);
  }, []);

  const navigateMaterials = useCallback((subpage: MaterialSubpage, replace = false) => {
    setMaterialSubpage(subpage); setAppStage('materials');
    const path = subpage === 'preparation' ? '/materials/preparation' : '/materials';
    if (window.location.pathname !== path) window.history[replace ? 'replaceState' : 'pushState']({ stage: 'materials', subpage }, '', path);
  }, []);

  const navigateExport = useCallback((subpage: ExportSubpage, replace = false) => {
    setExportSubpage(subpage);
    setAppStage('exports');
    const path = `/exports/${subpage}`;
    if (window.location.pathname !== path) window.history[replace ? 'replaceState' : 'pushState']({ stage: 'exports', subpage }, '', path);
  }, []);

  useEffect(() => {
    const onPopState = () => {
      setAppStage(stageFromPath(window.location.pathname));
      setExportSubpage(exportSubpageFromPath(window.location.pathname));
      setMaterialSubpage(materialSubpageFromPath(window.location.pathname));
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const removeRun = async (runId: string) => {
    setError(null);
    try {
      await workflowApi.deleteRun(runId);
      setRuns((current) => {
        const next = current.filter((item) => item.id !== runId);
        if (selectedRunId === runId) setSelectedRunId(next[0]?.id || null);
        return next;
      });
    } catch (reason) { setError(getErrorMessage(reason)); }
  };

  const refresh = useCallback(async () => {
    const response = await workflowApi.listRuns();
    setRuns(response.items); setSelectedRunId((value) => value || response.items[0]?.id || null);
  }, []);
  const refreshModel = useCallback(async () => {
    const model = await modelSettingsApi.get();
    setModelSettings(model);
    setModelLabel(model.provider === 'mock' ? '本地演示模型' : model.model);
    setModelRefreshKey((value) => value + 1);
  }, []);

  useEffect(() => {
    Promise.all([refresh(), refreshModel()]).catch((reason) => setError(getErrorMessage(reason))).finally(() => setLoading(false));
  }, [refresh, refreshModel]);

  const loadArchive = useCallback(async (archiveId: string) => {
    setArchiveLoading(true); setError(null);
    try { setSelectedArchive(await courseArchiveApi.get(archiveId)); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setArchiveLoading(false); }
  }, []);

  const refreshArchives = useCallback(async () => {
    const response = await courseArchiveApi.list();
    setArchives(response.items);
    if (response.items.length && !selectedArchive) await loadArchive(response.items[0].id);
  }, [loadArchive, selectedArchive]);

  const loadDesign = useCallback(async (designId: string) => {
    setDesignLoading(true); setError(null);
    try { setActiveDesign(await courseDesignApi.get(designId)); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setDesignLoading(false); }
  }, []);

  const refreshDesigns = useCallback(async () => {
    const response = await courseDesignApi.list();
    setDesigns(response.items);
    if (response.items.length && !activeDesign) await loadDesign(response.items[0].id);
  }, [activeDesign, loadDesign]);

  useEffect(() => {
    void refreshArchives().catch((reason) => setError(getErrorMessage(reason)));
  }, []);
  useEffect(() => {
    void refreshDesigns().catch((reason) => setError(getErrorMessage(reason)));
  }, []);

  useEffect(() => {
    // 仅当"用户没有主动点选会话"时, 才把 activeDesign 未绑定的残留 run 选择清掉;
    // 否则会误清用户刚点击的历史会话(design_id 与 activeDesign 不绑定也属正常)。
    if (activeDesign && !activeDesign.run_id && selectedRunId && userSelectedRunRef.current !== selectedRunId) setSelectedRunId(null);
  }, [activeDesign, selectedRunId]);

  useEffect(() => {
    if (!activeDesign?.knowledge_outline_id || activeDesign.run_id || parsedDoc || hydratedDesignId.current === activeDesign.id) return;
    hydratedDesignId.current = activeDesign.id;
    void courseArchiveApi.prepare(activeDesign.archive_id, {
      chapter: activeDesign.chapter,
      schedule_id: activeDesign.schedule_id,
      session_label: activeDesign.content.session_label,
      material_ids: activeDesign.material_ids,
      primary_material_id: activeDesign.primary_material_id,
    }).then((pack) => {
      setParsedDoc({
        ...pack.parsed_document,
        course_name: activeDesign.content.topic,
        knowledge_points: activeDesign.content.knowledge_points.map((point) => ({
          title: point,
          chapter: activeDesign.content.chapter,
          is_key_point: activeDesign.content.key_points.includes(point),
          difficulty_level: activeDesign.content.difficult_points.includes(point) ? '困难' : '标准',
          keywords: [],
        })),
      });
      setTitle(activeDesign.content.topic);
      setContext(`已导入资料单元知识大纲 v${activeDesign.knowledge_outline_version || 1}。${activeDesign.content.session_label || ''}`.trim());
      setSelectedRunId(null);
      setWorkspaceView('material');
      setProjectPanelOpen(true);
    }).catch((reason) => {
      hydratedDesignId.current = null;
      setError(getErrorMessage(reason));
    });
  }, [activeDesign, parsedDoc]);

  useEffect(() => {
    if (!uploading) return;
    const startedAt = Date.now();
    setUploadElapsed(0);
    const timer = window.setInterval(() => setUploadElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [uploading]);
  useEffect(() => {
    if (!archiveImporting) return;
    const startedAt = Date.now();
    setArchiveElapsed(0);
    const timer = window.setInterval(() => setArchiveElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [archiveImporting]);
  const selectedRun = useMemo(() => runs.find((item) => item.id === selectedRunId) || null, [runs, selectedRunId]);
  const onTerminal = useCallback(() => { void refresh(); }, [refresh]);
  const { events, connection } = useWorkflowEvents(selectedRunId, selectedRun?.status, onTerminal);

  const submitResume = async (action: ResumeInput['action']) => {
    if (!selectedRun) return;
    setResuming(true); setError(null);
    try {
      await workflowApi.resumeRun(selectedRun.id, { action, content: resumeText.trim() });
      setResumeText('');
      await refresh();
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setResuming(false); }
  };

  const appendRound = async () => {
    if (!selectedRun) return;
    setResuming(true); setError(null);
    try {
      await workflowApi.continueRun(selectedRun.id, 1, resumeText.trim());
      setResumeText('');
      await refresh();
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setResuming(false); }
  };

  const teaching = useMemo(() => eventTeachingData(selectedRun, events), [selectedRun, events]);
  const messages = teaching.messages || [];
  const messageGroups = useMemo(() => groupByIteration(messages), [messages]);
  const latestIteration = messageGroups[messageGroups.length - 1]?.iteration ?? 0;
  const previewDocument = useMemo(() => {
    if (parsedDoc) return {
      documentId: parsedDoc.document_id,
      fileName: parsedDoc.file_name,
      courseName: parsedDoc.course_name,
      rawText: parsedDoc.raw_text,
      sections: parsedDoc.sections,
      extractionReport: parsedDoc.extraction_report,
      characterCount: parsedDoc.character_count,
      processedCharacterCount: parsedDoc.processed_character_count,
      isTruncated: parsedDoc.is_truncated,
      analysis: undefined,
      defaultView: (activeDesign?.knowledge_outline_id ? 'text' : 'original') as 'text' | 'original',
      knowledge_outline_nodes: (activeDesign?.source_snapshot?.knowledge_nodes || []) as unknown as import('./types/workflow').MaterialUnitKnowledgeNode[],
      knowledge_outline_version: activeDesign?.knowledge_outline_version,
      onVisualEvidenceChange: setVisualEvidence,
    };
    if (selectedRun && teaching.document_text) return {
      documentId: teaching.document_id,
      fileName: teaching.document_name || '课程材料',
      courseName: selectedRun.objective,
      rawText: teaching.document_text,
      sections: teaching.document_sections,
      extractionReport: teaching.extraction_report,
      characterCount: teaching.document_text.length,
      processedCharacterCount: teaching.document_text.length,
      isTruncated: false,
      analysis: teaching.content_analysis,
      scope: teaching.scope,
    };
    return null;
  }, [parsedDoc, scope, selectedRun, teaching, activeDesign]);

  const parseFile = async (file: File) => {
    setUploadFileName(file.name); setUploading(true); setError(null); setVisualEvidence([]);
    try {
      const parsed = await documentApi.parse(file);
      setActiveDesign(null);
      setParsedDoc(parsed);
      setTitle(parsed.course_name);
      setSelectedRunId(null);
      setDetailTab('analysis');
      setWorkspaceView('material');
      setProjectPanelOpen(true);
    }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setUploading(false); }
  };
  const uploadStage = uploadElapsed < 8
    ? '正在读取并上传文件'
    : uploadElapsed < 25
      ? '正在提取正文、标题和版面结构'
      : '正在深度解析；扫描件会逐页进行 OCR';
  const uploadElapsedText = uploadElapsed < 60
    ? `${uploadElapsed} 秒`
    : `${Math.floor(uploadElapsed / 60)} 分 ${uploadElapsed % 60} 秒`;
  const archiveImportStatus = `正在建立索引 ${archiveImportCounts.content} / ${archiveImportCounts.total}${archiveElapsed ? ` · ${archiveElapsed} 秒` : ''}`;

  const importArchiveFolder = async (inputFiles: File[], navigateAfter = true, targetArchiveId?: string | null, sourceId?: string | null, sourceName?: string, onProgress?: (done: number, total: number) => void, directoryPaths: string[] = [], parentFolderId?: string | null): Promise<{ archiveId: string; sourceId: string } | null> => {
    const allFiles = relevantArchiveFiles(inputFiles);
    if (!allFiles.length && !sourceName?.trim()) { setError('没有读取到可建立索引的文件或文件夹。'); return null; }
    const archiveName = sourceName?.trim() || archivePath(allFiles[0]).split('/')[0] || '学期资料库';
    const indexedItems = Math.max(1, allFiles.length + directoryPaths.length);
    setArchiveImportCounts({ total: indexedItems, content: 0 });
    onProgress?.(0, indexedItems);
    setArchiveImporting(true); setError(null); if (navigateAfter) navigateStage('materials');
    try {
      const selectedTarget = archives.find((item) => item.id === targetArchiveId);
      const relativePath = (file: File) => {
        const parts = archivePath(file).replace(/\\/g, '/').split('/').filter(Boolean);
        return parts.length > 1 ? parts.slice(1).join('/') : file.name;
      };
      const registered = await dataHubApi.registerBrowserSource({
        archive_id: targetArchiveId || null,
        source_id: sourceId || null,
        source_name: archiveName,
        academic_term: selectedTarget?.academic_term || '',
        course_title: selectedTarget?.course_title || archiveName,
        course_code: selectedTarget?.course_code || '',
        selection_kind: !allFiles.length || directoryPaths.length > 0 || allFiles.some((file) => !!file.webkitRelativePath) ? 'folder' : 'files',
        manifest: allFiles.map((file) => ({ path: relativePath(file), size: file.size, last_modified: file.lastModified })),
        directories: directoryPaths,
        parent_folder_id: sourceId ? undefined : parentFolderId || null,
      });
      const indexedCount = Math.max(1, Math.round(indexedItems * 0.7));
      setArchiveImportCounts({ total: indexedItems, content: indexedCount });
      onProgress?.(indexedCount, indexedItems);
      const cachePrefix = `${registered.archive_id}:${registered.source.id}:`;
      for (const key of indexedSourceFiles.current.keys()) {
        if (key.startsWith(cachePrefix)) indexedSourceFiles.current.delete(key);
      }
      allFiles.forEach((file) => indexedSourceFiles.current.set(
        `${cachePrefix}${relativePath(file).toLocaleLowerCase()}`, file,
      ));
      setArchiveImportCounts({ total: indexedItems, content: indexedItems });
      onProgress?.(indexedItems, indexedItems);
      const detail = await courseArchiveApi.get(registered.archive_id);
      setSelectedArchive(detail);
      const response = await courseArchiveApi.list();
      setArchives(response.items);
      return { archiveId: detail.id, sourceId: registered.source.id };
    } catch (reason) {
      setError(getErrorMessage(reason));
      return null;
    }
    finally { setArchiveImporting(false); }
  };

  const prepareArchive = async (input: PrepareArchiveInput) => {
    if (!selectedArchive) return;
    setArchivePreparing(true); setArchiveImportCounts({ total: 0, content: 0 }); setError(null);
    try {
      const selected = selectedArchive.materials.filter((item) => input.material_ids.includes(item.id));
      const pendingBrowserFiles = selected.filter((item) => !item.document_id && item.source_kind === 'upload');
      const pendingUploads = pendingBrowserFiles.map((item) => ({
        item,
        file: item.source_folder_id && item.source_relative_path
          ? indexedSourceFiles.current.get(`${selectedArchive.id}:${item.source_folder_id}:${item.source_relative_path.toLocaleLowerCase()}`)
          : undefined,
      }));
      const unavailable = pendingUploads.filter((entry) => !entry.file);
      if (unavailable.length) {
        const examples = unavailable.slice(0, 3).map((entry) => entry.item.name).join('、');
        setError(`有 ${unavailable.length} 份已索引资料需要重新授权原件（${examples}${unavailable.length > 3 ? '等' : ''}）。请返回数据中台，点击对应一级来源的刷新图标并重新选择原文件或文件夹。`);
        return;
      }
      const groups = new Map<string, Array<{ file: File; path: string }>>();
      pendingUploads.forEach(({ item, file }) => {
        if (!file || !item.source_folder_id) return;
        const entries = groups.get(item.source_folder_id) || [];
        entries.push({ file, path: item.path });
        groups.set(item.source_folder_id, entries);
      });
      let imported = 0;
      const totalPending = pendingUploads.length;
      setArchiveImportCounts({ total: totalPending, content: 0 });
      for (const [sourceId, entries] of groups) {
        let batch: Array<{ file: File; path: string }> = [];
        let batchBytes = 0;
        const flush = async () => {
          if (!batch.length) return;
          await dataHubApi.uploadSourceFiles(selectedArchive.id, sourceId, batch);
          imported += batch.length;
          setArchiveImportCounts({ total: totalPending, content: imported });
          batch = []; batchBytes = 0;
        };
        for (const entry of entries) {
          if (batch.length >= 100 || (batch.length > 0 && batchBytes + entry.file.size > 72 * 1024 * 1024)) await flush();
          batch.push(entry); batchBytes += entry.file.size;
        }
        await flush();
      }
      const extracted = await courseArchiveApi.extract(selectedArchive.id, input.material_ids);
      setSelectedArchive(extracted);
      const [pack, design]: [PreparationPack, CourseDesignRecord] = await Promise.all([
        courseArchiveApi.prepare(selectedArchive.id, input),
        courseDesignApi.create({ ...input, archive_id: selectedArchive.id }),
      ]);
      setParsedDoc(pack.parsed_document);
      setTitle(pack.title);
      setContext(pack.context);
      setSelectedRunId(null);
      setVisualEvidence([]);
      setDetailTab('analysis');
      setWorkspaceView('material');
      setProjectPanelOpen(true);
      setActiveDesign(design);
      setDesigns((current) => [designSummary(design), ...current.filter((item) => item.id !== design.id)]);
      navigateStage('design');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setArchivePreparing(false); }
  };

  const removeArchive = async (archiveId: string, confirmed = false): Promise<ArchiveDeletionResult | null> => {
    if (!confirmed && !window.confirm('删除当前课程资料库及其平台副本、教学设计、资料包和关联会话？本机源目录不会被删除。')) return null;
    setError(null);
    let result: ArchiveDeletionResult;
    try {
      result = await courseArchiveApi.delete(archiveId);
    } catch (reason) { setError(getErrorMessage(reason)); return null; }
    try {
      const [archiveResponse, designResponse, runResponse] = await Promise.all([
        courseArchiveApi.list(), courseDesignApi.list(), workflowApi.listRuns(),
      ]);
      setArchives(archiveResponse.items);
      setDesigns(designResponse.items);
      setRuns(runResponse.items);
      setSelectedRunId((current) => runResponse.items.some((item) => item.id === current) ? current : runResponse.items[0]?.id || null);
      if (activeDesign?.archive_id === archiveId) {
        setActiveDesign(null);
      }
      if (archiveResponse.items.length) await loadArchive(archiveResponse.items[0].id);
      else setSelectedArchive(null);
    } catch (reason) { setError(`课程已删除，但列表刷新失败：${getErrorMessage(reason)}`); }
    return result;
  };
  const createSession = async () => {
    if (!parsedDoc || title.trim().length < 2) { setError('请先上传课程文档并填写课程标题。'); return; }
    if (scope.selected_point_titles.length === 0) { setError('请至少选择一个需要打磨的知识点。'); return; }
    if (!scopeConfirmed) { setError('请先核对知识点、课时和讲解深度，并确认本次范围。'); return; }
    setSubmitting(true); setError(null);
    try {
      const baseContext = context.trim().slice(0, 7800);
      const visualContext = visualEvidenceContext(visualEvidence).slice(0, 2000);
      const enrichedContext = [baseContext, visualContext].filter(Boolean).join('\n\n');
      const run = await workflowApi.createRun({ title: title.trim(), archive_id: activeDesign?.archive_id, design_id: activeDesign?.id, document_id: parsedDoc.document_id, document_name: parsedDoc.file_name, document_text: parsedDoc.raw_text, document_sections: parsedDoc.sections || [], extraction_report: parsedDoc.extraction_report, knowledge_points: editedPoints, max_iterations: iterations, context: enrichedContext, template_id: 'teaching_design', interventions, scope });
      setRuns((current) => [run, ...current]); setSelectedRunId(run.id); setParsedDoc(null); setTitle(''); setContext('');
      // 把新 run 绑定到当前课程设计, 使 run_id 非空:
      // 否则第 490 行的"清空未绑定 run"effect 会把刚选中的新 run 误清, 导致生成过程空白。
      setActiveDesign((current) => current ? { ...current, run_id: run.id } : current);
      setDesigns((current) => current.map((item) => item.id === activeDesign?.id ? { ...item, run_id: run.id } : item));
      setWorkspaceView('process');
      navigateStage('design');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setSubmitting(false); }
  };
  const resetForm = () => { setSelectedRunId(null); setParsedDoc(null); setActiveDesign(null); setTitle(''); setContext(''); setVisualEvidence([]); setScope({ selected_point_titles: [], estimated_minutes: 45, depth: 'standard' }); setScopeConfirmed(false); setWorkspaceView('material'); setProjectPanelOpen(true); setError(null); };

  /** 上传/载入课程后，把自动抽取的知识点同步为可编辑副本。 */
  useEffect(() => {
    if (parsedDoc) {
      const importedOutline = Boolean(activeDesign?.knowledge_outline_id);
      setSelectedRunId(null);
      setEditedPoints(parsedDoc.knowledge_points);
      const keyPoints = parsedDoc.knowledge_points.filter((point) => point.is_key_point).map((point) => point.title);
      const selectedPoints = importedOutline
        ? parsedDoc.knowledge_points.map((point) => point.title)
        : (keyPoints.length ? keyPoints : parsedDoc.knowledge_points.slice(0, 3).map((point) => point.title));
      setScope({ selected_point_titles: selectedPoints, estimated_minutes: 45, depth: 'standard' });
      setScopeConfirmed(importedOutline && parsedDoc.knowledge_points.length > 0);
    } else setEditedPoints([]);
  }, [activeDesign?.knowledge_outline_id, parsedDoc]);

  useEffect(() => {
    const available = new Set(editedPoints.map((point) => point.title));
    setScope((current) => ({ ...current, selected_point_titles: current.selected_point_titles.filter((title) => available.has(title)) }));
  }, [editedPoints]);

  const openFilePicker = useCallback(() => {
    fileInput.current?.click();
  }, []);

  const loadDemo = useCallback(() => {
    setActiveDesign(null);
    setParsedDoc(DEMO_COURSE);
    setTitle(DEMO_COURSE.course_name);
    setSelectedRunId(null);
    setDetailTab('analysis');
    setWorkspaceView('material');
    setProjectPanelOpen(true);
    setContext('');
    setVisualEvidence([]);
    setIterations(2);
    setInterventions({ after_design: false, after_question: false });
    setError(null);
  }, []);
  const selectRun = useCallback((runId: string) => {
    userSelectedRunRef.current = runId;
    setSelectedRunId(runId);
    setWorkspaceView('process');
    navigateStage('design');
  }, [navigateStage]);
  useEffect(() => {
    if (!selectedRunId) return;
    setDetailPanelOpen(false);
    setMessageView('latest');
  }, [selectedRunId]);
  const liveNode = useMemo(() => {
    const latestStarted = [...events].reverse().find((event) => event.event_type === 'node.started' && event.node)?.node;
    if (selectedRun?.status === 'completed' || selectedRun?.status === 'failed' || selectedRun?.status === 'cancelled') {
      return selectedRun.current_node || latestStarted || 'finalize';
    }
    return latestStarted || selectedRun?.current_node || 'content_analysis';
  }, [events, selectedRun?.current_node, selectedRun?.status]);
  const activePhase = liveNode;
  const completedNodes = new Set(events.filter((event) => ['node.completed', 'review.completed'].includes(event.event_type)).map((event) => event.node));
  const displayRunStatus = selectedRun?.status === 'queued' && events.some((event) => event.event_type === 'node.started') ? 'running' : selectedRun?.status;

  // 生成过程日志: 把 node.started/completed/run.heartbeat 解析成"后端在做什么"的时间线, 供等待空态展示。
  const processLogEntries = useMemo(() => {
    const logs: Array<{ sequence: number; node: string; message: string; time: string; completed: boolean; kind: 'start' | 'heartbeat' | 'done' }> = [];
    const nodeLabels: Record<string, string> = {
      content_analysis: '内容剖析', teaching_design: '教学设计', teach_knowledge: '教师讲授',
      student_question: '学生提问', teacher_answer: '教师答疑', supervisor_comment: '督导点评', finalize: '成果汇总',
    };
    events.forEach((event) => {
      if (event.event_type === 'node.started' && event.node) {
        logs.push({ sequence: event.sequence, node: event.node, message: event.message || `开始${nodeLabels[event.node] || event.node}`, time: new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false }), completed: false, kind: 'start' });
      } else if (event.event_type === 'node.completed' || event.event_type === 'review.completed') {
        if (event.node) logs.push({ sequence: event.sequence, node: event.node, message: `完成${nodeLabels[event.node] || event.node}`, time: new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false }), completed: true, kind: 'done' });
      } else if (event.event_type === 'run.heartbeat' && event.node) {
        logs.push({ sequence: event.sequence, node: event.node, message: event.message || '智能体仍在处理当前任务', time: new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false }), completed: false, kind: 'heartbeat' });
      }
    });
    return logs.slice(-12);
  }, [events]);


  const exportReport = async (format: 'md' | 'pdf', variant: 'teacher' | 'student' = 'teacher') => {
    if (!selectedRun) return;
    setError(null);
    try {
      const response = await fetch(workflowApi.reportUrl(selectedRun.id, format, variant));
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail || `导出失败（HTTP ${response.status}）`);
      }
      const disposition = response.headers.get('Content-Disposition') || '';
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const fallbackName = `${selectedRun.objective}-教学设计成果.${format}`;
      const filename = encodedName ? decodeURIComponent(encodedName) : fallbackName;
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '导出失败，请稍后重试。');
    }
  };

  const workspaceTitle = selectedRun?.objective || parsedDoc?.course_name || activeDesign?.title || '请选择或创建课程';
  const workspaceSubtitle = selectedRun ? (teaching.document_name || '课程材料') : parsedDoc ? parsedDoc.file_name : '从资料整理阶段确认来源后，再预览范围并启动多智能体教学设计。';
  if (loading) return <div className="app-loading"><div className="brand-mark"><BookOpen size={19} /></div><div><strong>课程教学智能体平台</strong><span>正在载入教学工作区</span></div><Loader2 className="spin" size={18} /></div>;

  return (
    <div className={`app-shell ${appStage === 'overview' ? 'overview-shell' : ''}`}>
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><BookOpen size={18} /></div><div><strong>课程教学智能体平台</strong><span>LangGraph Teaching Studio</span></div></div>
        <div className="topbar-meta">
          <span className={`connection connection-${connection}`}><Radio size={13} />{connection === 'live' ? '课堂实时同步' : selectedRun ? '本地记录' : '工作区就绪'}</span>
          <ModelQuickSwitcher settings={modelSettings} refreshKey={modelRefreshKey} onChanged={(model) => { setModelSettings(model); setModelLabel(model.provider === 'mock' ? '本地演示模型' : model.model); setModelRefreshKey((value) => value + 1); }} onOpenSettings={() => setShowSettings(true)} />
          <button className="icon-button" type="button" onClick={() => void refresh()} title="刷新教学会话" aria-label="刷新教学会话"><RefreshCw size={16} /></button>
        </div>
      </header>

      {appStage !== 'overview' && <StageNavigation stage={appStage} onChange={navigateStage} archiveCount={archives.length} runCount={runs.length} designCount={designs.length} />}
      <input ref={fileInput} id="course-file" type="file" accept=".pdf,.docx,.pptx,.md,.txt" className="visually-hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void parseFile(file); event.target.value = ''; }} />

      {appStage === 'overview' ? (
        <DataHubDashboard archives={archives} designs={designs} runs={runs} onNavigate={navigateStage} />
      ) : appStage === 'hub' ? (
        <DataHubWorkspace
          archives={archives}
          onOpenArchive={(archiveId) => { void loadArchive(archiveId); navigateMaterials('preparation'); }}
          onDataChanged={() => void refreshArchives()}
          onImportFolder={(files, archiveId, sourceId, sourceName, onProgress, directoryPaths, parentFolderId) => importArchiveFolder(files, false, archiveId, sourceId, sourceName, onProgress, directoryPaths, parentFolderId)}
          onDeleteArchive={(archiveId) => removeArchive(archiveId, true)}
          onMaterialUnitImported={() => setMaterialUnitRefreshKey((value) => value + 1)}
        />
      ) : appStage === 'materials' ? (
        materialSubpage === 'units' ? <MaterialUnitWorkspace
          refreshKey={materialUnitRefreshKey}
          onGoLibrary={() => navigateStage('hub')}
          onCourseDesignCreated={async (design) => {
            const pack = await courseArchiveApi.prepare(design.archive_id, {
              chapter: design.chapter,
              schedule_id: design.schedule_id,
              session_label: design.content.session_label,
              material_ids: design.material_ids,
              primary_material_id: design.primary_material_id,
            });
            hydratedDesignId.current = design.id;
            setActiveDesign(design);
            setParsedDoc({
              ...pack.parsed_document,
              course_name: design.content.topic,
              knowledge_points: design.content.knowledge_points.map((point) => ({
                title: point,
                chapter: design.content.chapter,
                is_key_point: design.content.key_points.includes(point),
                difficulty_level: design.content.difficult_points.includes(point) ? '困难' : '标准',
                keywords: [],
              })),
            });
            setTitle(design.content.topic);
            setContext(`已导入资料单元知识大纲 v${design.knowledge_outline_version || 1}。${design.content.session_label || ''}`.trim());
            setSelectedRunId(null);
            setWorkspaceView('material');
            setProjectPanelOpen(true);
            setDesigns((current) => [designSummary(design), ...current.filter((item) => item.id !== design.id)]);
            navigateStage('design');
          }}
        /> : <main className="stage-page materials-stage">
          <header className="stage-page-header"><div><span>备课资料选择</span><h1>确认教学使用范围</h1><p>原有的使用资料与主材料选择保持不变；资料单元中的分析结果可作为上游依据。</p></div><button type="button" className="secondary-button" onClick={() => navigateMaterials('units')}><FolderOpen size={15} />返回资料单元</button></header>
          <CourseArchiveWorkspace summaries={archives} archive={selectedArchive} loading={archiveLoading} importing={archiveImporting} preparing={archivePreparing} prepareProgress={{ done: archiveImportCounts.content, total: archiveImportCounts.total }} importStatus={archiveImportStatus} onImport={() => navigateStage('hub')} onSelectArchive={(archiveId) => void loadArchive(archiveId)} onDeleteArchive={(archiveId) => void removeArchive(archiveId)} onPrepare={(input) => void prepareArchive(input)} />
        </main>
      ) : appStage === 'exports' && exportSubpage === 'compose' ? (
        <CompositionWorkspace
          pendingBlocks={pendingHubBlocks}
          onPendingConsumed={() => setPendingHubBlocks([])}
          onOpenStructuredDesign={() => navigateExport('lesson')}
        />
      ) : appStage === 'exports' ? (
        <ExportWorkspace
          designs={designs}
          design={activeDesign}
          runs={runs}
          loading={designLoading}
          onSelect={(designId) => void loadDesign(designId)}
          onUpdated={(design) => {
            setActiveDesign(design);
            setDesigns((current) => current.map((item) => item.id === design.id ? designSummary(design) : item));
          }}
          onRefresh={() => void refreshDesigns()}
          onGoMaterials={() => navigateStage('materials')}
          onGoDesign={() => navigateStage('design')}
        />
      ) : (
      <main className={`workspace workspace-view-${workspaceView} ${projectPanelOpen ? 'project-open' : 'project-closed'} ${detailPanelOpen ? 'detail-open' : 'detail-closed'}`}>
        {projectPanelOpen && <aside className="left-panel">
          <div className="panel-heading"><div><span className="eyebrow">教学项目</span><h1>课程设计</h1></div><button className="icon-button" type="button" onClick={resetForm} title="新建课程" aria-label="新建课程"><Plus size={17} /></button></div>
          <section className="session-form" aria-label="创建教学设计会话">
            {!parsedDoc ? (
              <label htmlFor="course-file" className={`upload-zone ${uploading ? 'is-busy' : ''}`}><span>{uploading ? <Loader2 className="spin" size={19} /> : <Upload size={19} />}</span><strong>{uploading ? `${uploadStage} · ${uploadElapsedText}` : '上传课程材料'}</strong><small>{uploading ? uploadFileName : 'PDF、DOCX、PPTX、Markdown、TXT · 最大 30 MB'}</small></label>
            ) : (
              <div className="uploaded-file"><FileCheck2 size={19} /><div><strong>{parsedDoc.file_name}</strong><small>{parsedDoc.character_count.toLocaleString()} 字 · {parsedDoc.knowledge_points.length} 个候选知识点</small></div><button type="button" onClick={() => setParsedDoc(null)} title="移除文档" aria-label="移除文档"><X size={15} /></button></div>
            )}
            <button type="button" className="archive-folder-trigger" onClick={() => navigateStage('materials')} disabled={archiveImporting}><FolderOpen size={15} /><span>{archiveImporting ? archiveImportStatus : '前往资料整理与分析'}</span>{archives.length > 0 && !archiveImporting && <small>{archives.length}</small>}</button>
            {parsedDoc && <details className="knowledge-editor-disclosure"><summary><span><ListChecks size={14} />编辑候选知识点</span><small>{editedPoints.length} 项</small><ChevronDown size={14} /></summary><KnowledgePointEditor points={editedPoints} onChange={setEditedPoints} /></details>}
            {parsedDoc && <TeachingScopePlanner points={editedPoints} scope={scope} confirmed={scopeConfirmed} onConfirm={() => setScopeConfirmed(true)} onChange={(nextScope) => { setScope(nextScope); setScopeConfirmed(false); }} />}
            <label>课程标题<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="上传后自动识别，也可修改" /></label>
            <label>补充教学要求<textarea value={context} onChange={(event) => setContext(event.target.value)} rows={2} placeholder="可选：学情、课时或教学侧重点" /></label>
            <div className="iteration-setting"><span>教学迭代</span><div className="segmented">{[1, 2, 3].map((value) => <button key={value} type="button" className={iterations === value ? 'active' : ''} onClick={() => setIterations(value)}>{value} 轮</button>)}</div></div>
            <div className="intervention-setting">
              <span>我要参与<small>不勾选则全自动运行</small></span>
              <label className="check"><input type="checkbox" checked={interventions.after_design} onChange={(event) => setInterventions((value) => ({ ...value, after_design: event.target.checked }))} /><Hand size={13} />教学设计后暂停，与我沟通重难点</label>
              <label className="check"><input type="checkbox" checked={interventions.after_question} onChange={(event) => setInterventions((value) => ({ ...value, after_question: event.target.checked }))} /><Hand size={13} />学生提问后暂停，我可参与答疑</label>
            </div>
            {parsedDoc && <div className="duration-hint"><Clock3 size={12} />{modelLabel === '本地演示模型' ? '本地演示模型约 10 秒完成；真实模型 1 轮约 2-3 分钟，可随时停止' : '真实模型 1 轮约 2-3 分钟，可随时停止'}</div>}
            <button className="primary-button" type="button" onClick={() => void createSession()} disabled={!parsedDoc || submitting || title.trim().length < 2 || scope.selected_point_titles.length === 0 || !scopeConfirmed}>{submitting ? <Loader2 className="spin" size={16} /> : <Play size={15} fill="currentColor" />}启动教学设计</button>
          </section>
          <section className="runs-section"><div className="section-title"><span>教学会话</span><span>{runs.length}</span></div><div className="run-list">
            {runs.length === 0 ? <div className="empty-state"><Clock3 size={20} /><span>尚无教学会话</span></div> : runs.map((run) => (
              <SessionRunCard
                key={run.id}
                run={run}
                selected={selectedRunId === run.id}
                onSelect={() => selectRun(run.id)}
                onDelete={() => void removeRun(run.id)}
              />
            ))}
          </div></section>
        </aside>}

        <button
          className="project-panel-toggle icon-button"
          type="button"
          onClick={() => setProjectPanelOpen((value) => !value)}
          title={projectPanelOpen ? '收起课程与会话' : '展开课程与会话'}
          aria-label={projectPanelOpen ? '收起课程与会话' : '展开课程与会话'}
          aria-expanded={projectPanelOpen}
        >
          {projectPanelOpen ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
        </button>

        <section className="teaching-panel">
          <div className="teaching-top">
          <header className="teaching-header"><div><span className="eyebrow">教师教学工作区</span><h2>{workspaceTitle}</h2><p>{workspaceSubtitle}</p>{selectedRun && <TeachingProgress run={selectedRun} currentNode={liveNode} currentIteration={teaching.current_iteration} />}</div>{selectedRun && displayRunStatus && <div className="run-controls"><span className={`status-badge status-${displayRunStatus}`}>{displayRunStatus === 'running' && <Loader2 className="spin" size={13} />}{statusLabel(displayRunStatus)}</span>{selectedRun.final_output && <button className="secondary-button" type="button" onClick={() => navigateExport('lesson')} title="打开当前教案定稿"><FileDown size={15} />编辑与导出</button>}{!terminalStatuses.has(selectedRun.status) && <button className="secondary-button danger" type="button" onClick={() => void workflowApi.cancelRun(selectedRun.id).then(refresh)}><StopCircle size={15} />停止</button>}</div>}</header>
            {activeDesign && <div className="design-source-bar"><div><Link2 size={14} /><span>当前课程设计引用 <strong>{activeDesign.source_references.length}</strong> 条上游数据</span><small>第 {activeDesign.version} 版 · {activeDesign.run_id ? '已关联生成会话' : '待关联生成会话'}</small></div><button type="button" onClick={() => navigateStage('materials')}>核对资料</button><button type="button" onClick={() => navigateExport('lesson')}>打开教案定稿</button></div>}
            {workspaceView === 'process' && selectedRun && ['queued', 'running'].includes(selectedRun.status) && <GenerationStatusPanel run={selectedRun} events={events} connection={connection} />}
            <nav className="workspace-tabs" aria-label="工作区页面">
             <button type="button" className={workspaceView === 'material' ? 'active' : ''} onClick={() => setWorkspaceView('material')} disabled={!previewDocument}><FileText size={15} /><span>材料预览</span><small>目录与分析覆盖</small></button>
            <button type="button" className={workspaceView === 'process' ? 'active' : ''} onClick={() => setWorkspaceView('process')}><Radio size={15} /><span>生成过程</span><small>实时进度与对话</small></button>
            <button type="button" className={workspaceView === 'result' ? 'active' : ''} onClick={() => setWorkspaceView('result')} disabled={!selectedRun?.final_output}><FileDown size={15} /><span>教学成果</span><small>预览、编辑与导出</small></button>
           </nav>
          </div>

          {workspaceView === 'material' ? (
            previewDocument ? <DocumentPreviewWorkspace {...previewDocument} /> : activeDesign ? (
              <div className="empty-state tall"><FileCheck2 size={22} /><strong>材料预览正在加载</strong><span>已导入知识大纲 v{activeDesign.knowledge_outline_version || 1}，正在准备 {activeDesign.material_ids.length} 份已解析材料的正文预览…</span></div>
            ) : <WelcomePanel onUpload={openFilePicker} onDemo={loadDemo} />
          ) : workspaceView === 'result' ? (
            <div className="full-result-view"><ResultPanel run={selectedRun} onExport={exportReport} onError={setError} /></div>
          ) : (
            <div className="process-view">
              <div className="phase-rail">{phases.map((phase, index) => { const active = activePhase === phase.key; const done = completedNodes.has(phase.key) || selectedRun?.status === 'completed'; return <div key={phase.key} className={`phase-step ${active ? 'active' : ''} ${done ? 'done' : ''}`}><span>{done ? <CheckCircle2 size={14} /> : index + 1}</span><div><strong>{phase.name}</strong><small>{phase.short}</small></div></div>; })}</div>
              {selectedRun && messages.length > 0 && <div className="process-explorer"><div className="process-explorer-label"><ScanSearch size={14} /><span>局部查看</span><small>从全局流程定位到单轮内容</small></div><div className="round-switch" role="tablist" aria-label="教学轮次">{messageGroups.map((group) => { const active = messageView !== 'all' && group.iteration === (messageView === 'latest' ? latestIteration : messageView); return <button type="button" key={group.iteration} className={active ? 'active' : ''} onClick={() => setMessageView(group.iteration)}>{group.iteration === 0 ? '教学准备' : `第 ${group.iteration} 轮`}</button>; })}<button type="button" className={messageView === 'all' ? 'active' : ''} onClick={() => setMessageView('all')}>完整记录</button></div><button type="button" className={`insight-toggle ${detailPanelOpen ? 'active' : ''}`} onClick={() => setDetailPanelOpen((value) => !value)} aria-pressed={detailPanelOpen}>{detailPanelOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}课程洞察</button></div>}
               <div className="classroom-stream" aria-live="polite">
                 {!selectedRun ? (activeDesign ? (
                   <div className="empty-state tall"><FileCheck2 size={22} /><strong>课程设计已就绪</strong><span>已导入知识大纲 v{activeDesign.knowledge_outline_version || 1} 与 {activeDesign.material_ids.length} 份已解析材料，引用 {activeDesign.source_references.length} 条上游数据。请在左侧完善课程标题并选择知识点，点击「启动教学设计」开始智能体生成。</span></div>
                 ) : parsedDoc ? (
                   <div className="empty-state tall"><FileCheck2 size={22} /><strong>课程材料已就绪</strong><span>可切换到“材料预览”检查原文，再从左侧启动教学设计。</span></div>
                 ) : (
                   <WelcomePanel onUpload={openFilePicker} onDemo={loadDemo} />
                 )) : messages.length === 0 ? (
                   <div className="empty-state process-waiting process-log">
                     <div className="process-log-head"><Loader2 className={selectedRun.status === 'running' ? 'spin' : ''} size={22} /><div><strong>正在建立第一份分析结果</strong><span>{selectedRun.status === 'failed' ? `运行失败：${selectedRun.error || '模型未返回可解析结果'}` : '当前节点正在用 dsh 智能体处理，请稍候'}</span></div></div>
                     {selectedRun.status === 'running' || selectedRun.status === 'queued' ? (
                       <div className="process-log-list">{processLogEntries.length ? processLogEntries.map((entry, index) => <div key={`${entry.sequence}-${index}`} className="process-log-row"><i className={entry.completed ? 'done' : entry.kind} /><span>{entry.message || entry.node}<small>{entry.time}</small></span></div>) : <div className="process-log-row waiting"><i className="waiting" /><span>等待后端心跳，正在连接实时进度…<small>首次响应通常需要几十秒</small></span></div>}</div>
                     ) : null}
                   </div>
                 ) : (
                   <AgentFlowWorkspace
                     run={selectedRun}
                     events={events}
                     messages={messages}
                   />
                 )}
                 {(selectedRun?.status === 'paused' && selectedRun.pending_input) && <div className="process-action-zone"><InterventionPanel pending={selectedRun.pending_input} value={resumeText} onChange={setResumeText} busy={resuming} onSubmit={submitResume} /></div>}
                 {selectedRun?.status === 'completed' && <div className="process-action-zone"><div className="intervene-card next-round"><header><Repeat size={15} /><strong>打磨同一教学设计</strong><small>下一轮保留当前知识范围，先按督导建议重做教学设计，再生成新的讲授方案</small></header><textarea value={resumeText} onChange={(event) => setResumeText(event.target.value)} rows={2} placeholder="可选：补充本轮要优化的教学策略、示例或时间分配；留空则沿用督导提示词" /><div className="intervene-actions"><button type="button" className="primary-button" disabled={resuming} onClick={() => void appendRound()}>{resuming ? <Loader2 className="spin" size={15} /> : <Repeat size={15} />}再跑一轮</button></div></div></div>}
               </div>
            </div>
          )}
        </section>

        {workspaceView === 'process' && detailPanelOpen && <aside className="detail-panel">
          <div className="detail-tabs detail-tabs-three" role="tablist"><button className={detailTab === 'analysis' ? 'active' : ''} onClick={() => setDetailTab('analysis')}><Layers3 size={14} />重难点</button><button className={detailTab === 'framework' ? 'active' : ''} onClick={() => setDetailTab('framework')}><FileText size={14} />教学环节</button><button className={detailTab === 'review' ? 'active' : ''} onClick={() => setDetailTab('review')}><ShieldCheck size={14} />督导评价</button></div>
          <div className="detail-content">{detailTab === 'analysis' && <AnalysisPanel data={teaching} />}{detailTab === 'framework' && <FrameworkPanel data={teaching} />}{detailTab === 'review' && <ReviewPanel run={selectedRun} events={events} />}</div>
        </aside>}
      </main>
      )}
      {showSettings && <ModelSettingsPanel onClose={() => setShowSettings(false)} onSaved={() => void refreshModel()} />}
      {error && <div className="error-banner" role="alert"><AlertCircle size={16} /><span>{error}</span><button type="button" onClick={() => setError(null)}>关闭</button></div>}
    </div>
  );
}

function AnalysisPanel({ data }: { data: TeachingData }) {
  const analysis = data.content_analysis;
  if (!analysis) return <div className="empty-state tall"><Layers3 size={21} /><strong>尚未完成内容剖析</strong><span>教师智能体将从上传材料中识别知识结构。</span></div>;
  const copyText = [analysis.summary, `教学重点：${analysis.key_points?.join('；') || ''}`, `学习难点：${analysis.difficult_points?.join('；') || ''}`, `常见误区：${analysis.learner_misconceptions?.join('；') || ''}`].join('\n\n');
  return <div className="analysis-view"><div className="panel-copy-row"><strong>课程内容剖析</strong><CopyTextButton text={copyText} label="复制内容剖析" /></div><p className="analysis-summary">{analysis.summary}</p><DetailList title="教学重点" items={analysis.key_points} tone="green" /><DetailList title="学习难点" items={analysis.difficult_points} tone="amber" /><DetailList title="常见误区" items={analysis.learner_misconceptions} tone="red" /><div className="knowledge-cloud">{data.knowledge_points?.map((point) => <span key={point.title} className={point.is_key_point ? 'key' : ''}>{point.title}</span>)}</div></div>;
}
function CopyTextButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return <button type="button" className="copy-text-button" disabled={!text.trim()} onClick={() => void navigator.clipboard.writeText(text).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1400); }).catch(() => undefined)} title={label} aria-label={label}>{copied ? <CheckCircle2 size={12} /> : <Copy size={12} />}{copied ? '已复制' : '复制'}</button>;
}
function DetailList({ title, items = [], tone }: { title: string; items?: string[]; tone: string }) { return <section className={`detail-section tone-${tone}`}><h3><span>{title}</span><span className="detail-section-tools"><CopyTextButton text={items.join('\n')} label={`复制${title}`} /><small>{items.length}</small></span></h3><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></section>; }
const exerciseLevelNames: Record<string, string> = { low: '基础', medium: '进阶', high: '拓展' };
interface ExerciseItem { level: 'low' | 'medium' | 'high'; question: string; answer: string; }
function ExerciseCard({ exercise, index }: { exercise: ExerciseItem; index: number }) {
  return (
    <div className="exercise-card">
      <header><span className="exercise-no">{index + 1}</span><span className={`exercise-level level-${exercise.level}`}>{exerciseLevelNames[exercise.level]}</span></header>
      <p className="exercise-question">{exercise.question}</p>
      <details className="exercise-answer"><summary>查看参考答案</summary><div>{exercise.answer}</div></details>
    </div>
  );
}
function FrameworkPanel({ data }: { data: TeachingData }) {
  const framework = data.teaching_framework;
  if (!framework) return <div className="empty-state tall"><FileText size={21} /><strong>尚未形成教学环节</strong><span>内容剖析完成后将生成教学框架。</span></div>;
  const copyText = [`学习目标：\n${framework.learning_objectives?.join('\n') || ''}`, `教学环节：\n${framework.stages?.map((stage) => `${stage.name}（${stage.minutes}分钟）：${stage.activity}`).join('\n') || ''}`, `评价方式：\n${framework.assessment?.join('\n') || ''}`].join('\n\n');
  return <div className="framework-view"><div className="panel-copy-row"><strong>当前教学设计</strong><CopyTextButton text={copyText} label="复制教学设计" /></div><DetailList title="学习目标" items={framework.learning_objectives} tone="green" /><div className="stage-list">{framework.stages?.map((stage, index) => <div className="stage-item" key={`${stage.name}-${index}`}><span>{index + 1}</span><div><strong>{stage.name}<small>{stage.minutes} 分钟</small></strong><p>{stage.activity}</p><em>{stage.purpose}</em></div></div>)}</div>{framework.exercises?.length ? <section className="detail-section"><h3><span>课堂练习</span><span className="detail-section-tools"><CopyTextButton text={framework.exercises.map((item) => `${item.question}\n参考：${item.answer}`).join('\n\n')} label="复制课堂练习" /><small>{framework.exercises.length}</small></span></h3><div className="exercise-list">{framework.exercises.map((exercise, index) => <ExerciseCard key={`${exercise.question}-${index}`} exercise={exercise} index={index} />)}</div></section> : null}<DetailList title="评价方式" items={framework.assessment} tone="amber" /></div>;
}
function ReviewPanel({ run, events }: { run: WorkflowRun | null; events: RunEvent[] }) {
  const eventReview = [...events].reverse().find((event) => event.payload.review)?.payload.review as WorkflowRun['review'] | undefined;
  const review = run?.review || eventReview;
  if (!review) return <div className="empty-state tall"><ShieldCheck size={21} /><strong>等待督导评价</strong><span>完成首轮讲授和答疑后生成。</span></div>;
  return <div className="review-view"><div className="score-block"><strong>{review.score ?? '--'}</strong><span>本轮综合评分</span></div><div className="dimension-list">{Object.entries(review.dimensions || {}).map(([name, score]) => <div key={name}><span>{name}</span><div><i style={{ width: `${score}%` }} /></div><strong>{score}</strong></div>)}</div><DetailList title="教学亮点" items={review.strengths} tone="green" /><DetailList title="主要不足" items={review.weaknesses} tone="amber" /><DetailList title="改进建议" items={review.suggestions} tone="red" />{review.next_focus && <div className="next-focus"><MessageCircleQuestion size={16} /><div><strong>下一轮教学重点</strong><p>{review.next_focus}</p></div></div>}{review.iteration_prompt && <section className="reusable-prompt"><header><strong>可复用优化提示词</strong><CopyTextButton text={review.iteration_prompt} label="复制可复用优化提示词" /></header><p>{review.iteration_prompt}</p></section>}</div>;
}

function ResultPanel({ run, onExport, onError }: { run: WorkflowRun | null; onExport: (format: 'md' | 'pdf', variant?: 'teacher' | 'student') => void; onError: (message: string) => void }) {
  const report = run?.final_output;
  if (!report) return <div className="empty-state tall"><FileDown size={21} /><strong>尚未生成教学成果</strong><span>全部教学轮次完成后，这里将汇总课程剖析、学习目标与督导结论。</span></div>;
  return <TeacherMaterialsWorkspace run={run} onExport={onExport} onError={onError} />;
}

export default App;
