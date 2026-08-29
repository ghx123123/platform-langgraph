import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle, Archive, Check, CheckCircle2, Clipboard, Download, ExternalLink, Eye, FileInput,
  FileOutput, FileText, History, ListPlus, Loader2, RefreshCw, Save, ShieldCheck, Trash2, Upload,
} from 'lucide-react';
import { courseArchiveApi, courseDesignApi, documentApi, getErrorMessage } from '../lib/api';
import type {
  CourseArchiveDetail, CourseDesignAssemblySource, CourseDesignAssemblySourceKind, CourseDesignAssemblyTarget,
  CourseDesignContent, CourseDesignExportRecord, CourseDesignRecord, CourseDesignSummary,
  CourseDesignTemplateInspection, CourseReferenceDetail, WorkflowRun,
} from '../types/workflow';
import './ExportWorkspace.css';

interface Props {
  designs: CourseDesignSummary[];
  design: CourseDesignRecord | null;
  runs: WorkflowRun[];
  loading: boolean;
  onSelect: (designId: string) => void;
  onUpdated: (design: CourseDesignRecord) => void;
  onRefresh: () => void;
  onGoMaterials: () => void;
  onGoDesign: () => void;
}

const layerLabels = { original: '原始文件', extracted: '提取正文', structured: '结构化数据', generated: '生成成果' } as const;

function listText(items: string[]): string { return items.join('\n'); }
function textList(value: string): string[] { return value.split(/\r?\n/).map((item) => item.replace(/^\s*[-*\d.、]+\s*/, '').trim()).filter(Boolean); }

function filenameFromDisposition(value: string, fallback: string): string {
  const encoded = value.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  return encoded ? decodeURIComponent(encoded) : fallback;
}

function formatExportTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function templateOptionLabel(item: CourseArchiveDetail['materials'][number]): string {
  const parts = item.path.replace(/\\/g, '/').split('/').filter(Boolean);
  const parent = parts.length > 1 ? parts[parts.length - 2] : '';
  return `${item.name}${parent ? ` · ${parent}` : ''}${item.document_id ? '' : '（选择后加载）'}`;
}

const fieldLabels: Record<string, string> = {
  course_name: '课程名称', topic: '授课主题', chapter: '章节', session_label: '讲次', class_name: '班级', location: '地点', hours: '课时',
  objectives: '教学目标', knowledge_points: '知识点', key_points: '教学重点', difficult_points: '教学难点', methods: '教学方法', tools: '教学手段',
  ideological_elements: '课程思政', teaching_process: '教学过程', assessment: '评价设计', postscript: '教学后记',
};
const sourceKindLabels: Record<CourseDesignAssemblySourceKind, string> = {
  schedule: '进度表', syllabus: '教学大纲', knowledge_outline: '知识大纲', teacher_message: '教师智能体',
  teacher_draft: '教师审核稿', ideological: '思政建议', custom: '教师填写',
};
const assemblyTargets: CourseDesignAssemblyTarget[] = ['session_label', 'objectives', 'knowledge_points', 'key_points', 'difficult_points', 'methods', 'tools', 'teaching_process', 'assessment', 'ideological_elements', 'postscript'];

export function ExportWorkspace({ designs, design, runs, loading, onSelect, onUpdated, onRefresh, onGoMaterials, onGoDesign }: Props) {
  const templateInput = useRef<HTMLInputElement>(null);
  const [content, setContent] = useState<CourseDesignContent | null>(design?.content || null);
  const [archive, setArchive] = useState<CourseArchiveDetail | null>(null);
  const [status, setStatus] = useState<'draft' | 'reviewed'>(design?.status || 'draft');
  const [templateMaterialId, setTemplateMaterialId] = useState(design?.template_material_id || '');
  const [templateDocumentId, setTemplateDocumentId] = useState<string | null>(design?.template_document_id || null);
  const [templateName, setTemplateName] = useState('内置标准教案模板');
  const [templateQuery, setTemplateQuery] = useState('');
  const [runId, setRunId] = useState(design?.run_id || '');
  const [assemblySources, setAssemblySources] = useState<CourseDesignAssemblySource[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [sourceKind, setSourceKind] = useState<'all' | CourseDesignAssemblySourceKind>('all');
  const [assemblyTarget, setAssemblyTarget] = useState<CourseDesignAssemblyTarget>('teaching_process');
  const [assemblyMode, setAssemblyMode] = useState<'replace' | 'prepend' | 'append'>('append');
  const [assemblyPreviewId, setAssemblyPreviewId] = useState('');
  const [assemblyLoading, setAssemblyLoading] = useState(false);
  const [sourceDetail, setSourceDetail] = useState<CourseReferenceDetail | null>(null);
  const [inspection, setInspection] = useState<CourseDesignTemplateInspection | null>(null);
  const [inspectionLoading, setInspectionLoading] = useState(false);
  const [exports, setExports] = useState<CourseDesignExportRecord[]>(design?.exports || []);
  const [busy, setBusy] = useState<'save' | 'sync' | 'template' | 'export' | 'source' | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    setContent(design?.content || null);
    setStatus(design?.status || 'draft');
    setTemplateDocumentId(design?.template_document_id || null);
    setTemplateMaterialId(design?.template_material_id || '');
    setRunId(design?.run_id && runs.some((run) => run.id === design.run_id && run.status === 'completed') ? design.run_id : '');
    setAssemblySources([]); setSelectedSourceIds([]); setAssemblyPreviewId(''); setSourceKind('all');
    setSourceDetail(null);
    setExports(design?.exports || []);
    setInspection(null);
    if (!design) { setArchive(null); return; }
    void courseArchiveApi.get(design.archive_id).then(setArchive).catch((reason) => setError(getErrorMessage(reason)));
  }, [design?.id, design?.version]);

  const templateMaterials = useMemo(() => archive?.materials.filter((item) => item.category === 'lesson_plan' && item.extension === '.docx') || [], [archive]);
  const filteredTemplateMaterials = useMemo(() => {
    const query = templateQuery.trim().toLocaleLowerCase();
    if (!query) return templateMaterials;
    return templateMaterials.filter((item) => `${item.name} ${item.path}`.toLocaleLowerCase().includes(query) || item.id === templateMaterialId);
  }, [templateMaterialId, templateMaterials, templateQuery]);
  useEffect(() => {
    if (templateMaterialId) {
      setTemplateName(templateMaterials.find((item) => item.id === templateMaterialId)?.name || '资料库模板');
    } else if (templateDocumentId) setTemplateName('已上传自定义模板');
    else setTemplateName('内置标准教案模板');
  }, [templateDocumentId, templateMaterialId, templateMaterials]);
  useEffect(() => {
    if (!design) return;
    let active = true;
    setInspectionLoading(true);
    void courseDesignApi.inspectTemplate(design.id, { template_material_id: templateMaterialId || null, template_document_id: templateDocumentId })
      .then((result) => { if (active) { setInspection(result); setError(''); } })
      .catch((reason) => { if (active) { setInspection(null); setError(getErrorMessage(reason)); } })
      .finally(() => { if (active) setInspectionLoading(false); });
    return () => { active = false; };
  }, [design?.id, design?.version, templateDocumentId, templateMaterialId]);
  const completedRuns = runs.filter((run) => {
    if (run.status !== 'completed' || !design) return false;
    const data = run.teaching_data || {};
    if (data.design_id) return data.design_id === design.id;
    if (data.archive_id) return data.archive_id === design.archive_id;
    return !!data.document_id && design.source_references.some((item) => item.document_id === data.document_id);
  });
  const visibleAssemblySources = sourceKind === 'all' ? assemblySources : assemblySources.filter((item) => item.kind === sourceKind);
  const assemblyPreview = assemblySources.find((item) => item.id === assemblyPreviewId);
  const setField = <K extends keyof CourseDesignContent>(key: K, value: CourseDesignContent[K]) => setContent((current) => current ? { ...current, [key]: value } : current);

  const save = async (nextStatus = status): Promise<CourseDesignRecord | null> => {
    if (!design || !content) return null;
    setBusy('save'); setError(''); setMessage('');
    try {
      const updated = await courseDesignApi.update(design.id, content, nextStatus, design.version, templateDocumentId, templateMaterialId || null);
      onUpdated(updated); setStatus(updated.status); setMessage(`已保存第 ${updated.version} 版`); return updated;
    } catch (reason) { setError(getErrorMessage(reason)); return null; }
    finally { setBusy(null); }
  };

  const syncRun = async () => {
    if (!design || !runId) return;
    setBusy('sync'); setError(''); setMessage('');
    try { const updated = await courseDesignApi.syncRun(design.id, runId); onUpdated(updated); setMessage('已引用所选多智能体成果并生成新版本'); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const loadAssemblySources = async (selectedRunId = runId, announce = true) => {
    if (!design) return;
    setAssemblyLoading(true); setError('');
    try {
      const result = await courseDesignApi.assemblySources(design.id, selectedRunId || undefined);
      setAssemblySources(result.items); setSelectedSourceIds([]); setAssemblyPreviewId(result.items[0]?.id || '');
      if (announce) setMessage(`已读取 ${result.items.length} 项可插入内容`);
    } catch (reason) { setAssemblySources([]); setError(getErrorMessage(reason)); }
    finally { setAssemblyLoading(false); }
  };

  useEffect(() => {
    if (design) void loadAssemblySources('', false);
  }, [design?.id, design?.version]);

  const toggleAssemblySource = (item: CourseDesignAssemblySource) => {
    setSelectedSourceIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id]);
    setAssemblyPreviewId(item.id);
    if (selectedSourceIds.length === 0) setAssemblyTarget(item.default_target);
  };

  const applyAssemblySources = async () => {
    if (!design || !content || selectedSourceIds.length === 0) return;
    setBusy('sync'); setError(''); setMessage('');
    try {
      let current = design;
      const dirty = JSON.stringify(content) !== JSON.stringify(design.content)
        || templateDocumentId !== design.template_document_id
        || templateMaterialId !== (design.template_material_id || '');
      if (dirty) {
        current = await courseDesignApi.update(design.id, content, status, design.version, templateDocumentId, templateMaterialId || null);
        onUpdated(current);
      }
      const updated = await courseDesignApi.applyAssembly(current.id, {
        base_version: current.version, source_ids: selectedSourceIds, target_field: assemblyTarget, mode: assemblyMode,
      }, runId || undefined);
      onUpdated(updated); setSelectedSourceIds([]);
      setMessage(`已插入到“${fieldLabels[assemblyTarget]}”，保存为第 ${updated.version} 版`);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const uploadTemplate = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.docx')) { setError('教案模板必须为 DOCX 文件。'); return; }
    setBusy('template'); setError(''); setMessage('');
    try {
      const parsed = await documentApi.parse(file);
      setTemplateDocumentId(parsed.document_id); setTemplateMaterialId(''); setTemplateName(file.name);
      setMessage('模板已保存，正在检查可填充字段和原格式兼容性');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const selectTemplateMaterial = async (materialId: string) => {
    if (!materialId) {
      setTemplateMaterialId(''); setTemplateDocumentId(null); setTemplateName('内置标准教案模板'); return;
    }
    if (!design || !archive) return;
    const selected = templateMaterials.find((item) => item.id === materialId);
    if (!selected) return;
    setError(''); setMessage(''); setInspection(null);
    if (selected.document_id) {
      setTemplateMaterialId(materialId); setTemplateDocumentId(null); setTemplateName(selected.name); return;
    }
    setBusy('template');
    try {
      const updatedArchive = await courseArchiveApi.extract(design.archive_id, [materialId]);
      const loaded = updatedArchive.materials.find((item) => item.id === materialId);
      if (!loaded?.document_id) throw new Error(loaded?.parse_message || '模板原件按需加载失败');
      setArchive(updatedArchive); setTemplateMaterialId(materialId); setTemplateDocumentId(null); setTemplateName(loaded.name);
      setMessage('已从资料库按需加载模板原件，正在检查原格式兼容性');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const exportDocx = async () => {
    if (!design || !content) return;
    setBusy('export'); setError(''); setMessage('');
    try {
      let current = design;
      if (JSON.stringify(content) !== JSON.stringify(design.content) || templateDocumentId !== design.template_document_id || templateMaterialId !== (design.template_material_id || '')) {
        current = await courseDesignApi.update(design.id, content, status, design.version, templateDocumentId, templateMaterialId || null);
        onUpdated(current);
      }
      const result = await courseDesignApi.exportDocx(current.id, { template_material_id: templateMaterialId || null, template_document_id: templateDocumentId, filename: `${content.course_name}-${content.topic}-教案.docx`, preserve_source_format: true });
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a'); link.href = url; link.download = filenameFromDisposition(result.disposition, `${content.course_name}-教案.docx`);
      document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1200);
      const refreshed = await courseDesignApi.get(current.id);
      onUpdated(refreshed); setExports(refreshed.exports || []);
      setMessage(result.templateMode === 'source-template' ? '已保持所选模板格式导出，并保存到成果历史' : '已使用内置标准模板导出，并保存到成果历史');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const inspectSource = async (referenceId: string) => {
    if (!design) return;
    setBusy('source'); setError('');
    try { setSourceDetail(await courseDesignApi.source(design.id, referenceId)); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const deleteExport = async (item: CourseDesignExportRecord) => {
    if (!design || !window.confirm(`从平台删除导出成果“${item.filename}”？课程设计、资料库原件和模板不会被删除。`)) return;
    setError(''); setMessage('');
    try {
      await courseDesignApi.deleteExport(design.id, item.id);
      const refreshed = await courseDesignApi.get(design.id);
      onUpdated(refreshed); setExports(refreshed.exports || []); setMessage('已删除所选导出成果');
    } catch (reason) { setError(getErrorMessage(reason)); }
  };

  if (loading) return <div className="export-empty"><Loader2 className="spin" /><strong>正在读取课程设计稿</strong></div>;
  if (!design || !content) return (
    <main className="export-empty"><FileOutput size={28} /><h2>还没有可编辑的课程设计稿</h2><p>先在资料整理页确认章节、讲次、主材料和配套材料，系统会建立带来源引用的课程设计记录。</p><button className="primary-button compact" type="button" onClick={onGoMaterials}>前往资料整理</button></main>
  );

  return (
    <main className="export-workspace">
      <header className="export-header">
        <div><span>成果中心 · 教案定稿</span><h1>编辑并导出结构化教案</h1><p>当前稿的每个上游来源均可回到原始文件或提取正文。</p></div>
        <div className="export-actions"><button type="button" className="secondary-button" onClick={() => void save()} disabled={!!busy}><Save size={15} />保存版本</button><button type="button" className="primary-button compact" onClick={() => void exportDocx()} disabled={!!busy || !inspection?.compatible}>{busy === 'export' ? <Loader2 className="spin" size={15} /> : <Download size={15} />}{busy === 'export' ? '正在生成并保存' : '导出 DOCX'}</button></div>
      </header>
      {(message || error) && <div className={`export-notice ${error ? 'error' : ''}`}>{error ? <FileText size={14} /> : <CheckCircle2 size={14} />}{error || message}</div>}
      <div className="export-columns">
        <aside className="export-list">
          <div className="export-section-title"><span>课程设计稿</span><button type="button" onClick={onRefresh} title="刷新设计稿" aria-label="刷新设计稿"><RefreshCw size={14} /></button></div>
          <div className="design-record-list">{designs.map((item) => <button type="button" key={item.id} className={item.id === design.id ? 'active' : ''} onClick={() => onSelect(item.id)}><FileText size={14} /><span><strong>{item.title}</strong><small>第 {item.version} 版 · {item.source_count} 条引用 · {item.export_count || 0} 次导出</small></span>{item.status === 'reviewed' && <Check size={13} />}</button>)}</div>
          <div className="export-jump"><button type="button" onClick={onGoMaterials}><Archive size={14} />返回资料整理</button><button type="button" onClick={onGoDesign}><FileInput size={14} />返回课程设计</button></div>
        </aside>

        <section className="design-editor">
          <div className="editor-meta"><label>课程名称<input value={content.course_name} onChange={(event) => setField('course_name', event.target.value)} /></label><label>章节<input value={content.chapter} onChange={(event) => setField('chapter', event.target.value)} /></label><label className="wide">授课主题<input value={content.topic} onChange={(event) => setField('topic', event.target.value)} /></label><label className="wide">讲次与教学范围<input value={content.session_label} onChange={(event) => setField('session_label', event.target.value)} /></label><label>授课班级<input value={content.class_name} onChange={(event) => setField('class_name', event.target.value)} /></label><label>授课地点<input value={content.location} onChange={(event) => setField('location', event.target.value)} /></label><label>课时<input value={content.hours} onChange={(event) => setField('hours', event.target.value)} /></label></div>
          <div className="editor-block"><label>教学目标<small>每行一项</small></label><textarea rows={5} value={listText(content.objectives)} onChange={(event) => setField('objectives', textList(event.target.value))} /></div>
          <div className="editor-block"><label>知识点大纲<small>每行一项，导出时保持当前顺序</small></label><textarea rows={7} value={listText(content.knowledge_points)} onChange={(event) => setField('knowledge_points', textList(event.target.value))} /></div>
          <div className="editor-split"><div className="editor-block"><label>教学重点<small>每行一项</small></label><textarea rows={6} value={listText(content.key_points)} onChange={(event) => setField('key_points', textList(event.target.value))} /></div><div className="editor-block"><label>教学难点<small>每行一项</small></label><textarea rows={6} value={listText(content.difficult_points)} onChange={(event) => setField('difficult_points', textList(event.target.value))} /></div></div>
          <div className="editor-split"><div className="editor-block"><label>教学方法<small>每行一项</small></label><textarea rows={4} value={listText(content.methods)} onChange={(event) => setField('methods', textList(event.target.value))} /></div><div className="editor-block"><label>教学手段<small>每行一项</small></label><textarea rows={4} value={listText(content.tools)} onChange={(event) => setField('tools', textList(event.target.value))} /></div></div>
          <div className="editor-block"><label>教学过程<small>保留结构和分段，可在 Word 中继续编辑</small></label><textarea rows={15} value={content.teaching_process} onChange={(event) => setField('teaching_process', event.target.value)} /></div>
          <div className="editor-block"><label>评价设计</label><textarea rows={5} value={content.assessment} onChange={(event) => setField('assessment', event.target.value)} /></div>
          <div className="editor-block"><label>课程思政元素<small>每行一项</small></label><textarea rows={4} value={listText(content.ideological_elements)} onChange={(event) => setField('ideological_elements', textList(event.target.value))} /></div>
          <div className="editor-block postscript-editor"><label>教学后记<small>由教师在授课后填写，智能体同步不会覆盖</small></label><textarea rows={8} placeholder="记录目标达成、课堂实施、学生反馈及下一次改进方向" value={content.postscript} onChange={(event) => setField('postscript', event.target.value)} /></div>
        </section>

        <aside className="export-config">
          <section className="assembly-panel">
            <div className="export-section-title"><span>内容编排</span><ListPlus size={14} /></div>
            <label className="assembly-label">多智能体会话<select value={runId} onChange={(event) => { setRunId(event.target.value); void loadAssemblySources(event.target.value); }}><option value="">仅使用进度表、大纲和知识范围</option>{completedRuns.map((run) => <option key={run.id} value={run.id}>{run.objective}</option>)}</select></label>
            <div className="assembly-actions"><button type="button" className="secondary-button" disabled={!runId || !!busy} onClick={() => void syncRun()}><RefreshCw size={14} />整体同步框架</button><button type="button" className="secondary-button" disabled={assemblyLoading} onClick={() => void loadAssemblySources()}>{assemblyLoading ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}刷新内容</button></div>
            <div className="assembly-kinds"><button type="button" className={sourceKind === 'all' ? 'active' : ''} onClick={() => setSourceKind('all')}>全部</button>{(['schedule', 'syllabus', 'knowledge_outline', 'teacher_message', 'teacher_draft', 'ideological'] as CourseDesignAssemblySourceKind[]).filter((kind) => assemblySources.some((item) => item.kind === kind)).map((kind) => <button type="button" className={sourceKind === kind ? 'active' : ''} key={kind} onClick={() => setSourceKind(kind)}>{sourceKindLabels[kind]}</button>)}</div>
            <div className="assembly-source-list">{assemblyLoading ? <div className="assembly-empty"><Loader2 className="spin" size={15} />正在读取来源</div> : visibleAssemblySources.length ? visibleAssemblySources.map((item) => <label key={item.id} className={`${selectedSourceIds.includes(item.id) ? 'selected' : ''} ${assemblyPreviewId === item.id ? 'previewing' : ''}`}><input type="checkbox" checked={selectedSourceIds.includes(item.id)} onChange={() => toggleAssemblySource(item)} /><span onClick={() => setAssemblyPreviewId(item.id)}><strong>{item.title}</strong><small>{sourceKindLabels[item.kind]} · 建议插入{fieldLabels[item.default_target]}</small></span></label>) : <div className="assembly-empty">当前范围没有这一类可插入内容</div>}</div>
            {assemblyPreview && <div className="assembly-preview"><strong>{assemblyPreview.title}</strong><p>{assemblyPreview.content}</p><small>{assemblyPreview.source_name} · {assemblyPreview.locator}</small></div>}
            <div className="assembly-destination"><label>插入到<select value={assemblyTarget} onChange={(event) => setAssemblyTarget(event.target.value as CourseDesignAssemblyTarget)}>{assemblyTargets.map((target) => <option key={target} value={target}>{fieldLabels[target]}</option>)}</select></label><label>处理方式<select value={assemblyMode} onChange={(event) => setAssemblyMode(event.target.value as typeof assemblyMode)}><option value="append">追加到现有内容后</option><option value="prepend">插入到现有内容前</option><option value="replace">替换该区域</option></select></label></div>
            <button type="button" className="primary-button compact full" disabled={selectedSourceIds.length === 0 || !!busy} onClick={() => void applyAssemblySources()}>{busy === 'sync' ? <Loader2 className="spin" size={14} /> : <ListPlus size={14} />}插入所选 {selectedSourceIds.length || ''} 项内容</button>
          </section>
          <section className="template-panel"><div className="export-section-title"><span>Word 模板</span><FileOutput size={14} /></div><input className="template-search" value={templateQuery} onChange={(event) => setTemplateQuery(event.target.value)} placeholder={`搜索 ${templateMaterials.length} 份资料库模板`} /><select value={templateMaterialId} disabled={busy === 'template'} onChange={(event) => void selectTemplateMaterial(event.target.value)}><option value="">内置标准教案模板</option>{filteredTemplateMaterials.map((item) => <option key={item.id} value={item.id}>{templateOptionLabel(item)}</option>)}</select><input ref={templateInput} className="visually-hidden" type="file" accept=".docx" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadTemplate(file); event.target.value = ''; }} /><button type="button" className="secondary-button full" disabled={!!busy} onClick={() => templateInput.current?.click()}>{busy === 'template' ? <Loader2 className="spin" size={14} /> : <Upload size={14} />}{busy === 'template' ? '正在加载模板原件' : '上传其他 DOCX 模板'}</button><small className="template-name">当前：{templateName}</small>{inspectionLoading ? <div className="template-inspection checking"><Loader2 className="spin" size={15} /><span><strong>正在检查模板</strong><small>识别表格、正文、页眉和页脚中的填充位置</small></span></div> : inspection && <div className={`template-inspection ${inspection.compatible ? 'compatible' : 'incompatible'}`}>{inspection.compatible ? <ShieldCheck size={17} /> : <AlertTriangle size={17} />}<span><strong>{inspection.template_mode === 'source-template' ? inspection.compatible ? '可保持原格式导出' : '无法按原格式填充' : '内置模板字段完整'}</strong><small>{inspection.message}</small></span>{inspection.template_mode === 'source-template' && <div className="template-fields"><span>{inspection.matched_fields.length} 类字段</span><span>{inspection.table_count} 个表格</span><span>{inspection.header_count + inspection.footer_count} 个页眉页脚</span></div>}{inspection.matched_fields.length > 0 && <p>{inspection.matched_fields.slice(0, 8).map((item) => fieldLabels[item] || item).join('、')}{inspection.matched_fields.length > 8 ? '等' : ''}</p>}{!inspection.compatible && <button type="button" onClick={() => { setTemplateMaterialId(''); setTemplateDocumentId(null); setTemplateName('内置标准教案模板'); }}>改用内置标准模板</button>}</div>}</section>
          <section className="export-history"><div className="export-section-title"><span>导出成果</span><em>{exports.length}</em></div>{exports.length ? <div>{exports.slice().reverse().map((item) => <article key={item.id}><FileOutput size={15} /><span><strong title={item.filename}>{item.filename}</strong><small>设计 v{item.design_version} · {item.template_name}</small><small>{formatExportTime(item.created_at)} · {(item.size / 1024).toFixed(1)} KB</small></span><div><a href={item.preview_url} target="_blank" rel="noreferrer" title="原页预览" aria-label={`预览${item.filename}`}><Eye size={14} /></a><a href={item.download_url} title="下载 Word" aria-label={`下载${item.filename}`}><Download size={14} /></a><button type="button" onClick={() => void deleteExport(item)} title="删除导出记录" aria-label={`删除${item.filename}`}><Trash2 size={14} /></button></div></article>)}</div> : <p className="export-history-empty">尚未导出。导出后会保存设计版本、模板来源和可预览 Word。</p>}</section>
          <section className="source-chain"><div className="export-section-title"><span>数据引用链</span><em>{design.source_references.length}</em></div><div className="source-list">{design.source_references.map((reference) => <button type="button" key={reference.id} className={sourceDetail?.reference.id === reference.id ? 'active' : ''} onClick={() => void inspectSource(reference.id)}><span className={`source-layer layer-${reference.layer}`}>{layerLabels[reference.layer]}</span><strong>{reference.source_name}</strong><small>{reference.locator}</small>{reference.character_count > 0 && <em>{reference.character_count.toLocaleString()} 字</em>}</button>)}</div></section>
          {busy === 'source' && <div className="source-preview"><Loader2 className="spin" size={15} />正在读取引用内容</div>}
          {sourceDetail && <section className="source-preview"><header><strong>{sourceDetail.reference.source_name}</strong><div>{sourceDetail.reference.preview_url && <button type="button" onClick={() => window.open(sourceDetail.reference.preview_url!, '_blank', 'noopener,noreferrer')} title="原页预览"><ExternalLink size={13} /></button>}{sourceDetail.reference.original_url && <button type="button" onClick={() => window.open(sourceDetail.reference.original_url!, '_blank', 'noopener,noreferrer')} title="打开原文件"><FileInput size={13} /></button>}<button type="button" onClick={() => void navigator.clipboard.writeText(sourceDetail.content)} title="复制引用正文"><Clipboard size={13} /></button></div></header><pre>{sourceDetail.content.slice(0, 5000) || '该引用只保存来源定位，不包含提取正文。'}</pre>{sourceDetail.content.length > 5000 && <small>界面预览前 5,000 字，完整正文仍保存在后端引用记录中。</small>}</section>}
          <section className="review-status"><div className="export-section-title"><span>稿件状态</span><History size={14} /></div><div className="segmented"><button type="button" className={status === 'draft' ? 'active' : ''} onClick={() => setStatus('draft')}>编辑中</button><button type="button" className={status === 'reviewed' ? 'active' : ''} onClick={() => setStatus('reviewed')}>教师已审核</button></div><button type="button" className="secondary-button full" disabled={!!busy} onClick={() => void save(status)}>{busy === 'save' ? <Loader2 className="spin" size={14} /> : <Save size={14} />}保存当前状态</button></section>
        </aside>
      </div>
    </main>
  );
}
