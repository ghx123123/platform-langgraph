import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check, CheckCircle2, ChevronDown, ChevronUp, ClipboardPlus, Download, ExternalLink,
  Eye, FileOutput, FileText, Loader2, Pencil, Plus, Save, Search,
  Square, Trash2, Upload, X,
} from 'lucide-react';
import { dataHubApi, getErrorMessage } from '../lib/api';
import type { CompositionBlock, CompositionRecord, CompositionSummary, DataHubBlock, DataHubCatalog, DataHubBlockKind } from '../types/workflow';
import './CompositionWorkspace.css';

interface Props {
  pendingBlocks: DataHubBlock[];
  onPendingConsumed: () => void;
  onOpenStructuredDesign: () => void;
}

const kindLabels: Record<DataHubBlockKind, string> = {
  original: '原始文件', extracted: '提取正文', teaching_design: '教学设计', student_question: '学生问题',
  teacher_answer: '教师答疑', supervisor_review: '督导建议', ideological_element: '思政元素', imported: '导入内容',
};
type SourceGroup = 'all' | 'design' | 'question' | 'ideology' | 'material';
const sourceGroups: Array<{ id: SourceGroup; label: string; kinds?: DataHubBlockKind[] }> = [
  { id: 'all', label: '全部' },
  { id: 'design', label: '教学设计', kinds: ['teaching_design', 'supervisor_review'] },
  { id: 'question', label: '问答', kinds: ['student_question', 'teacher_answer'] },
  { id: 'ideology', label: '思政元素', kinds: ['ideological_element'] },
  { id: 'material', label: '原始资料', kinds: ['original', 'extracted', 'imported'] },
];

function blankComposition(): CompositionRecord {
  return { id: '', title: '未命名教学资料包', archive_id: null, unit_id: null, blocks: [], version: 1, created_at: '', updated_at: '' };
}

function downloadName(disposition: string, fallback: string) {
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  try { return encoded ? decodeURIComponent(encoded) : plain || fallback; } catch { return fallback; }
}

function mergeBlocks(base: CompositionRecord, sources: DataHubBlock[]): CompositionRecord {
  const existing = new Set(base.blocks.map((item) => item.source_block_id).filter(Boolean));
  const blocks = sources.filter((source) => !existing.has(source.id)).map((source): CompositionBlock => ({
    id: crypto.randomUUID(), source_block_id: source.id, kind: source.kind, title: source.title,
    content: source.content || source.content_preview, source_name: source.source_name, locator: source.locator,
  }));
  return {
    ...base,
    archive_id: base.archive_id || sources[0]?.archive_id,
    unit_id: base.unit_id || sources[0]?.unit_id,
    blocks: [...base.blocks, ...blocks],
  };
}

export function CompositionWorkspace({ pendingBlocks, onPendingConsumed, onOpenStructuredDesign }: Props) {
  const importInput = useRef<HTMLInputElement>(null);
  const [catalog, setCatalog] = useState<DataHubCatalog | null>(null);
  const [items, setItems] = useState<CompositionSummary[]>([]);
  const [record, setRecord] = useState<CompositionRecord>(blankComposition());
  const [mode, setMode] = useState<'edit' | 'preview'>('edit');
  const [sourceQuery, setSourceQuery] = useState('');
  const [sourceGroup, setSourceGroup] = useState<SourceGroup>('all');
  const [sourceScope, setSourceScope] = useState<'unit' | 'all'>('unit');
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [previewSource, setPreviewSource] = useState<DataHubBlock | null>(null);
  const [pendingTargetId, setPendingTargetId] = useState('new');
  const [busy, setBusy] = useState<'load' | 'save' | 'import' | 'export' | 'source' | null>('load');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const refresh = async () => {
    setBusy('load'); setError('');
    try {
      const [catalogResult, listResult] = await Promise.all([dataHubApi.catalog(), dataHubApi.listCompositions()]);
      setCatalog(catalogResult); setItems(listResult.items);
      if (!pendingBlocks.length && !record.id && listResult.items[0]) {
        const latest = await dataHubApi.getComposition(listResult.items[0].id);
        setRecord((current) => current.id || current.blocks.length ? current : latest);
      }
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };
  useEffect(() => { void refresh(); }, []);

  const visibleSources = useMemo(() => {
    const group = sourceGroups.find((item) => item.id === sourceGroup);
    return (catalog?.blocks || []).filter((item) => {
      if (group?.kinds && !group.kinds.includes(item.kind)) return false;
      if (sourceScope === 'unit' && record.unit_id && item.unit_id !== record.unit_id) return false;
      return !sourceQuery || `${item.title} ${item.source_name} ${item.content_preview}`.toLowerCase().includes(sourceQuery.toLowerCase());
    }).slice(0, 100);
  }, [catalog, record.unit_id, sourceGroup, sourceQuery, sourceScope]);
  const selectedSources = useMemo(() => selectedSourceIds.map((id) => catalog?.blocks.find((item) => item.id === id)).filter((item): item is DataHubBlock => !!item), [catalog, selectedSourceIds]);
  const selectedVisible = visibleSources.length > 0 && visibleSources.every((item) => selectedSourceIds.includes(item.id));

  const appendBlocks = (sources: DataHubBlock[]) => {
    setRecord((current) => mergeBlocks(current, sources));
    setMessage(`已加入 ${sources.length} 项来源内容，可在中栏继续编辑。`);
  };

  const loadAndAppend = async (sources: DataHubBlock[]) => {
    if (!sources.length) return;
    setBusy('source'); setError('');
    try {
      const details = await Promise.all(sources.map((source) => dataHubApi.block(source.id)));
      appendBlocks(details); setSelectedSourceIds([]); setMode('edit');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  useEffect(() => { if (pendingBlocks.length) setPendingTargetId('new'); }, [pendingBlocks]);

  const confirmPendingTarget = async () => {
    if (!pendingBlocks.length) return;
    setBusy('source'); setError('');
    try {
      const [base, ...details] = await Promise.all([
        pendingTargetId === 'new' ? Promise.resolve(blankComposition()) : dataHubApi.getComposition(pendingTargetId),
        ...pendingBlocks.map((source) => dataHubApi.block(source.id)),
      ]);
      setRecord(mergeBlocks(base, details));
      setMode('edit'); setMessage(`已将 ${details.length} 项内容加入${pendingTargetId === 'new' ? '新资料包' : '所选资料包'}，保存前不会覆盖其他成果。`);
      onPendingConsumed();
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const inspectSource = async (source: DataHubBlock) => {
    setBusy('source'); setError('');
    try { setPreviewSource(await dataHubApi.block(source.id)); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const selectComposition = async (id: string) => {
    setBusy('load'); setError(''); setSelectedSourceIds([]);
    try { setRecord(await dataHubApi.getComposition(id)); setMode('edit'); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const save = async (): Promise<CompositionRecord | null> => {
    if (!record.title.trim()) { setError('请填写成果名称。'); return null; }
    setBusy('save'); setError(''); setMessage('');
    try {
      const saved = record.id ? await dataHubApi.updateComposition(record) : await dataHubApi.createComposition({ title: record.title, archive_id: record.archive_id, unit_id: record.unit_id, blocks: record.blocks });
      setRecord(saved); setItems((current) => [{ id: saved.id, title: saved.title, archive_id: saved.archive_id, unit_id: saved.unit_id, version: saved.version, block_count: saved.blocks.length, updated_at: saved.updated_at }, ...current.filter((item) => item.id !== saved.id)]);
      setMessage(`已保存第 ${saved.version} 版教学资料包。`); return saved;
    } catch (reason) { setError(getErrorMessage(reason)); return null; }
    finally { setBusy(null); }
  };

  const importFile = async (file: File) => {
    setBusy('import'); setError(''); setMessage('');
    try {
      const imported = await dataHubApi.importComposition(file); setRecord(imported); setMode('edit');
      setItems((current) => [{ id: imported.id, title: imported.title, archive_id: imported.archive_id, unit_id: imported.unit_id, version: imported.version, block_count: imported.blocks.length, updated_at: imported.updated_at }, ...current.filter((item) => item.id !== imported.id)]);
      setMessage(`“${file.name}”已导入为可编辑内容，可查看原页并继续插入中台数据。`);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const exportFile = async (format: 'docx' | 'md' | 'json') => {
    const saved = await save(); if (!saved) return;
    setBusy('export'); setError('');
    try {
      const response = await fetch(dataHubApi.exportUrl(saved.id, format));
      if (!response.ok) throw new Error(`导出失败（HTTP ${response.status}）`);
      const blob = await response.blob();
      if (format === 'docx') {
        const contentType = response.headers.get('Content-Type') || blob.type;
        const signature = new Uint8Array(await blob.slice(0, 2).arrayBuffer());
        if (!contentType.includes('application/vnd.openxmlformats-officedocument.wordprocessingml.document') || signature[0] !== 0x50 || signature[1] !== 0x4b) {
          throw new Error('后端未返回有效的 Word 文档，请刷新后重试。');
        }
      }
      const url = URL.createObjectURL(blob); const link = document.createElement('a');
      let filename = downloadName(response.headers.get('Content-Disposition') || '', `${saved.title}.${format}`);
      if (!filename.toLowerCase().endsWith(`.${format}`)) filename = `${filename}.${format}`;
      link.href = url; link.download = filename;
      document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1200);
      setMessage(format === 'docx' ? `已导出可编辑 Word 文档“${filename}”。` : `已导出 ${format.toUpperCase()} 交换文件。`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const updateBlock = (id: string, changes: Partial<CompositionBlock>) => setRecord((current) => ({ ...current, blocks: current.blocks.map((item) => item.id === id ? { ...item, ...changes } : item) }));
  const moveBlock = (index: number, offset: number) => setRecord((current) => { const blocks = [...current.blocks]; const target = index + offset; if (target < 0 || target >= blocks.length) return current; [blocks[index], blocks[target]] = [blocks[target], blocks[index]]; return { ...current, blocks }; });
  const removeBlock = (id: string) => setRecord((current) => ({ ...current, blocks: current.blocks.filter((item) => item.id !== id) }));
  const addIdeologicalBlock = () => {
    const next: CompositionBlock = { id: crypto.randomUUID(), source_block_id: null, kind: 'ideological_element', title: '课程思政元素', content: '', source_name: '教师新增', locator: 'composition:draft' };
    setRecord((current) => ({ ...current, blocks: [...current.blocks, next] })); setMode('edit');
    setMessage('已新增思政元素内容块，保存后会回流数据中台。');
  };
  const removeComposition = async () => {
    if (!record.id || !window.confirm('删除当前教学资料包？原始资料和课程设计不会被删除。')) return;
    try { await dataHubApi.deleteComposition(record.id); setRecord(blankComposition()); await refresh(); }
    catch (reason) { setError(getErrorMessage(reason)); }
  };

  return <main className="composition-workspace">
    <header className="composition-header"><div><span>成果中心 · 教学资料包</span><h1>编辑并导出教学资料包</h1><p>组合不同来源的附件型内容；正式教案请进入“教案定稿”。</p></div><div><button type="button" className="secondary-button" onClick={onOpenStructuredDesign}><FileText size={15} />切换到教案定稿</button><button type="button" className="primary-button compact" disabled={!!busy} onClick={() => void save()}>{busy === 'save' ? <Loader2 className="spin" size={15} /> : <Save size={15} />}{busy === 'save' ? '正在保存…' : '保存版本'}</button></div></header>
    <nav className="composition-steps" aria-label="教学资料包制作流程"><span className={record.blocks.length ? 'done' : 'active'}><i>1</i><strong>选择内容</strong><small>{record.blocks.length} 项已加入</small></span><span className={mode === 'edit' && record.blocks.length ? 'active' : ''}><i>2</i><strong>编辑整理</strong><small>标题、正文与顺序</small></span><span className={mode === 'preview' ? 'active' : ''}><i>3</i><strong>预览导出</strong><small>可编辑 Word (.docx)</small></span></nav>
    {busy === 'load' && <div className="composition-loading-status" aria-live="polite"><Loader2 className="spin" size={14} /><span><strong>正在载入成果与统一内容库…</strong>完成后会恢复上次编辑内容。</span></div>}
    {(message || error) && <div className={`composition-notice ${error ? 'error' : ''}`} aria-live="polite">{error ? <X size={14} /> : <CheckCircle2 size={14} />}{error || message}</div>}
    <div className="composition-columns">
      <aside className="composition-list"><header><span>教学资料包</span><button type="button" onClick={() => { setRecord(blankComposition()); setMode('edit'); }} title="新建教学资料包" aria-label="新建教学资料包"><Plus size={15} /></button></header><div>{items.map((item) => <button type="button" key={item.id} className={record.id === item.id ? 'active' : ''} onClick={() => void selectComposition(item.id)}><FileOutput size={14} /><span><strong>{item.title}</strong><small>第 {item.version} 版 · {item.block_count} 个内容块</small></span></button>)}</div><input ref={importInput} className="visually-hidden" type="file" accept=".docx,.pdf,.pptx,.md,.txt,.json" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); event.target.value = ''; }} /><button type="button" className="secondary-button full" disabled={!!busy} onClick={() => importInput.current?.click()}>{busy === 'import' ? <Loader2 className="spin" size={14} /> : <Upload size={14} />}{busy === 'import' ? '正在识别文件…' : '导入文件并编辑'}</button>{record.import_preview_url && <button type="button" className="composition-import-preview" onClick={() => setPreviewSource({ id: 'import-preview', kind: 'imported', title: record.title, content_preview: '', content: '', source_name: record.title, locator: '导入原文件', preview_url: record.import_preview_url, original_url: record.import_original_url, editable: false, updated_at: record.updated_at })}><Eye size={14} />在页面内查看导入原页</button>}{record.id && <button type="button" className="composition-delete" onClick={() => void removeComposition()}><Trash2 size={14} />删除当前资料包</button>}</aside>
      <section className="composition-main">
        <div className="composition-title-row"><label>资料包名称<input name="composition-title" autoComplete="off" value={record.title} onChange={(event) => setRecord({ ...record, title: event.target.value })} /></label><div className="composition-tabs" role="tablist" aria-label="编辑或预览"><button type="button" role="tab" aria-selected={mode === 'edit'} className={mode === 'edit' ? 'active' : ''} onClick={() => setMode('edit')}><Pencil size={14} />编辑</button><button type="button" role="tab" aria-selected={mode === 'preview'} className={mode === 'preview' ? 'active' : ''} onClick={() => setMode('preview')}><Eye size={14} />预览</button></div></div>
        {record.blocks.length > 0 && <div className="composition-selected-strip"><strong>当前文档内容</strong><div>{record.blocks.map((item, index) => <button type="button" key={item.id} onClick={() => setMode('edit')} title={`定位到第 ${index + 1} 项：${item.title}`}><i>{index + 1}</i><span>{item.title}</span><X size={11} onClick={(event) => { event.stopPropagation(); removeBlock(item.id); }} /></button>)}</div></div>}
        {mode === 'edit' ? <div className="composition-editor">{record.blocks.length === 0 ? <div className="composition-empty"><ClipboardPlus size={27} /><strong>从右侧选择要组合的内容</strong><span>先勾选教学设计、原始资料或思政元素，再点击“加入当前资料包”。</span></div> : record.blocks.map((item, index) => <article key={item.id} className="composition-block"><header><span className={`hub-kind kind-${item.kind}`}>{kindLabels[item.kind]}</span><input aria-label={`第 ${index + 1} 项标题`} value={item.title} onChange={(event) => updateBlock(item.id, { title: event.target.value })} /><div><button type="button" disabled={index === 0} onClick={() => moveBlock(index, -1)} title="上移" aria-label={`上移${item.title}`}><ChevronUp size={14} /></button><button type="button" disabled={index === record.blocks.length - 1} onClick={() => moveBlock(index, 1)} title="下移" aria-label={`下移${item.title}`}><ChevronDown size={14} /></button><button type="button" onClick={() => removeBlock(item.id)} title="移除" aria-label={`移除${item.title}`}><X size={14} /></button></div></header><textarea aria-label={`${item.title}正文`} value={item.content} onChange={(event) => updateBlock(item.id, { content: event.target.value })} rows={Math.min(14, Math.max(5, item.content.split('\n').length + 2))} /><small>{item.source_name && `来源：${item.source_name}`}{item.locator && ` · ${item.locator}`}</small></article>)}</div> : <article className="composition-preview"><h1>{record.title}</h1>{record.blocks.length === 0 ? <div className="composition-empty"><Eye size={25} /><strong>暂无可预览内容</strong><span>请先切换到编辑页加入内容。</span></div> : record.blocks.map((item) => <section key={item.id}><span className={`hub-kind kind-${item.kind}`}>{kindLabels[item.kind]}</span><h2>{item.title}</h2><div>{item.content || '暂无内容'}</div>{item.source_name && <small>来源：{item.source_name} · {item.locator}</small>}</section>)}</article>}
        <footer className="composition-export-bar"><div>{record.id && <button type="button" onClick={() => window.open(dataHubApi.previewUrl(record.id), '_blank', 'noopener,noreferrer')}><ExternalLink size={14} />打印预览</button>}<span>{record.id ? `第 ${record.version} 版` : '尚未保存'}</span></div><div><details><summary>中台交换格式</summary><button type="button" onClick={() => void exportFile('md')}>Markdown</button><button type="button" onClick={() => void exportFile('json')}>JSON</button></details><button type="button" className="word-export-button" disabled={!!busy || record.blocks.length === 0} onClick={() => void exportFile('docx')}>{busy === 'export' ? <Loader2 className="spin" size={15} /> : <Download size={15} />}{busy === 'export' ? '正在生成 Word…' : '导出可编辑 Word (.docx)'}</button></div></footer>
      </section>
      <aside className="composition-sources"><header><div><span>统一内容库</span><em>{visibleSources.length}</em></div><button type="button" className="new-ideology-block" onClick={addIdeologicalBlock}><Plus size={13} />新增思政元素</button><label><Search size={14} aria-hidden="true" /><input name="source-search" autoComplete="off" value={sourceQuery} onChange={(event) => setSourceQuery(event.target.value)} placeholder="搜索可插入内容…" aria-label="搜索可插入内容" /></label><div className="source-scope"><button type="button" className={sourceScope === 'unit' ? 'active' : ''} disabled={!record.unit_id} onClick={() => setSourceScope('unit')}>当前单元</button><button type="button" className={sourceScope === 'all' ? 'active' : ''} onClick={() => setSourceScope('all')}>全部课程</button></div></header>
        <nav className="source-groups" aria-label="来源类型">{sourceGroups.map((group) => <button type="button" key={group.id} className={sourceGroup === group.id ? 'active' : ''} onClick={() => setSourceGroup(group.id)}>{group.label}</button>)}</nav>
        {selectedSources.length > 0 && <section className="source-selection"><div><CheckCircle2 size={14} /><strong>已勾选 {selectedSources.length} 项</strong><button type="button" onClick={() => setSelectedSourceIds([])}>清空</button></div><ul>{selectedSources.map((item) => <li key={item.id}><span>{item.title}</span><button type="button" onClick={() => setSelectedSourceIds((current) => current.filter((id) => id !== item.id))} aria-label={`取消选择${item.title}`}><X size={11} /></button></li>)}</ul><button type="button" className="primary-button compact" disabled={busy === 'source'} onClick={() => void loadAndAppend(selectedSources)}>{busy === 'source' ? <Loader2 className="spin" size={14} /> : <Plus size={14} />}加入当前资料包</button></section>}
        <div className="source-table-head"><button type="button" onClick={() => setSelectedSourceIds((current) => selectedVisible ? current.filter((id) => !visibleSources.some((item) => item.id === id)) : [...new Set([...current, ...visibleSources.map((item) => item.id)])])} aria-label={selectedVisible ? '取消选择当前来源' : '选择当前来源'}>{selectedVisible ? <Check size={13} /> : <Square size={13} />}</button><span>来源内容</span><span>预览</span></div>
        <div className="source-table">{visibleSources.length === 0 ? <div className="source-empty"><Search size={20} /><strong>没有匹配内容</strong><span>{sourceScope === 'unit' ? '可切换到“全部课程”扩大范围。' : '请调整类型或检索条件。'}</span></div> : visibleSources.map((item) => { const selected = selectedSourceIds.includes(item.id); const inserted = record.blocks.some((blockItem) => blockItem.source_block_id === item.id); return <div className={`source-row ${selected ? 'selected' : ''}`} key={item.id}><button type="button" onClick={() => setSelectedSourceIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} disabled={inserted} aria-label={inserted ? `${item.title}已加入` : selected ? `取消选择${item.title}` : `选择${item.title}`}>{inserted || selected ? <Check size={13} /> : <Square size={13} />}</button><div><span className={`hub-kind kind-${item.kind}`}>{inserted ? '已加入' : kindLabels[item.kind]}</span><strong>{item.title}</strong><small>{item.source_name || item.locator}</small></div><button type="button" onClick={() => void inspectSource(item)} title="预览来源" aria-label={`预览${item.title}`}><Eye size={14} /></button></div>; })}</div>
        {visibleSources.length === 100 && <small className="source-limit">显示前 100 项，请使用搜索缩小范围。</small>}
      </aside>
    </div>
    {previewSource && <aside className="composition-source-preview" aria-label="来源预览"><header><div><span className={`hub-kind kind-${previewSource.kind}`}>{kindLabels[previewSource.kind]}</span><strong>{previewSource.title}</strong><small>{previewSource.source_name}</small></div><button type="button" onClick={() => setPreviewSource(null)} aria-label="关闭来源预览"><X size={16} /></button></header><div>{previewSource.preview_url ? <iframe title={`${previewSource.title}原页预览`} src={previewSource.preview_url} /> : <pre>{previewSource.content || previewSource.content_preview || '该来源没有可显示的正文。'}</pre>}</div><footer>{previewSource.preview_url && <button type="button" onClick={() => window.open(previewSource.preview_url!, '_blank', 'noopener,noreferrer')}><ExternalLink size={14} />新窗口打开</button>}{previewSource.id !== 'import-preview' && <button type="button" className="primary-button compact" onClick={() => { setPreviewSource(null); void loadAndAppend([previewSource]); }}><Plus size={14} />加入成果</button>}</footer></aside>}
    {pendingBlocks.length > 0 && catalog && <div className="composition-target-backdrop" role="presentation"><section className="composition-target-dialog" role="dialog" aria-modal="true" aria-labelledby="composition-target-title"><header><div><span>确认数据去向</span><h2 id="composition-target-title">将 {pendingBlocks.length} 项内容加入哪里？</h2><p>平台不会再自动写入最近使用的成果，请明确选择目标。</p></div><button type="button" onClick={onPendingConsumed} aria-label="取消加入"><X size={16} /></button></header><div className="composition-target-files">{pendingBlocks.map((item) => <span key={item.id}><span className={`hub-kind kind-${item.kind}`}>{kindLabels[item.kind]}</span><strong>{item.title}</strong></span>)}</div><label>目标资料包<select value={pendingTargetId} onChange={(event) => setPendingTargetId(event.target.value)}><option value="new">新建教学资料包（推荐）</option>{items.map((item) => <option value={item.id} key={item.id}>追加到：{item.title} · 第 {item.version} 版</option>)}</select></label><footer><button type="button" className="secondary-button" onClick={onPendingConsumed}>取消</button><button type="button" className="primary-button compact" disabled={busy === 'source'} onClick={() => void confirmPendingTarget()}>{busy === 'source' ? <Loader2 className="spin" size={14} /> : <CheckCircle2 size={14} />}{busy === 'source' ? '正在读取并加入…' : '确认加入'}</button></footer></section></div>}
  </main>;
}
