import { useEffect, useMemo, useState } from 'react';
import {
  Check, CheckCircle2, Clock3, Copy, Download, FileDown, FileText,
  History, Loader2, Pencil, RotateCcw, Save, Sparkles,
} from 'lucide-react';
import { Markdown } from './Markdown';
import { getErrorMessage, workflowApi } from '../lib/api';
import type { TeacherDraft, TeacherDraftStatus, TeacherDraftVersion, WorkflowRun } from '../types/workflow';
import './TeacherMaterialsWorkspace.css';

interface MaterialSection {
  id: string;
  title: string;
  content: string;
}

interface Props {
  run: WorkflowRun;
  onExport: (format: 'md' | 'pdf', variant?: 'teacher' | 'student') => void;
  onError: (message: string) => void;
}

const localDraftKey = (runId: string) => `teacher-material-draft:${runId}`;

function splitSections(markdown: string): MaterialSection[] {
  const starts = [...markdown.matchAll(/^##\s+(.+)$/gm)];
  if (!starts.length) return [{ id: 'overview', title: '完整成果', content: markdown.trim() }];
  const sections: MaterialSection[] = [];
  const firstStart = starts[0].index || 0;
  if (markdown.slice(0, firstStart).trim()) {
    sections.push({ id: 'overview', title: '成果概览', content: markdown.slice(0, firstStart).trim() });
  }
  starts.forEach((match, index) => {
    const start = match.index || 0;
    const end = starts[index + 1]?.index ?? markdown.length;
    sections.push({
      id: `section-${index + 1}`,
      title: match[1].replace(/^\s*[一二三四五六七八九十]+[、.]\s*/, '').trim(),
      content: markdown.slice(start, end).trim(),
    });
  });
  return sections;
}

function joinSections(sections: MaterialSection[]) {
  return sections.map((section) => section.content.trim()).filter(Boolean).join('\n\n');
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

export function TeacherMaterialsWorkspace({ run, onExport, onError }: Props) {
  const [draft, setDraft] = useState<TeacherDraft | null>(null);
  const [sections, setSections] = useState<MaterialSection[]>([]);
  const [selectedId, setSelectedId] = useState('overview');
  const [versions, setVersions] = useState<TeacherDraftVersion[]>([]);
  const [mode, setMode] = useState<'preview' | 'edit'>('preview');
  const [instruction, setInstruction] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'save' | 'review' | 'generate' | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setNotice('');
    Promise.all([workflowApi.getTeacherDraft(run.id), workflowApi.listTeacherDraftVersions(run.id)])
      .then(([nextDraft, history]) => {
        if (!active) return;
        let content = nextDraft.content;
        const local = localStorage.getItem(localDraftKey(run.id));
        if (local) {
          try {
            const recovered = JSON.parse(local) as { baseVersion: number; content: string };
            if (recovered.baseVersion === nextDraft.version && recovered.content !== content) {
              content = recovered.content;
              setNotice('已恢复本机未保存的编辑');
              setMode('edit');
            }
          } catch { localStorage.removeItem(localDraftKey(run.id)); }
        }
        const nextSections = splitSections(content);
        // The workspace works on individual blocks and joins them with a
        // canonical separator. Keep the comparison baseline in that same
        // representation so an untouched generated report is never marked
        // as a local edit just because of harmless Markdown whitespace.
        setDraft({ ...nextDraft, content: joinSections(nextSections) });
        setSections(nextSections);
        setSelectedId(nextSections[0]?.id || 'overview');
        setVersions(history.items);
      })
      .catch((reason) => onError(getErrorMessage(reason)))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [run.id, onError]);

  const current = sections.find((section) => section.id === selectedId) || sections[0];
  const content = useMemo(() => joinSections(sections), [sections]);
  const dirty = Boolean(draft && content !== draft.content);
  const draftLabel = draft?.source === 'generated'
    ? '智能体原稿'
    : draft?.status === 'reviewed'
      ? '教师已审核'
      : dirty
        ? '有未保存修改'
        : '教师编辑稿';

  useEffect(() => {
    if (!draft || !dirty) return;
    localStorage.setItem(localDraftKey(run.id), JSON.stringify({ baseVersion: draft.version, content }));
  }, [content, dirty, draft, run.id]);

  const updateCurrent = (value: string) => {
    setSections((items) => items.map((section) => section.id === current?.id ? { ...section, content: value } : section));
    if (draft?.status === 'reviewed') setDraft({ ...draft, status: 'draft' });
  };

  const refreshVersions = async () => {
    const response = await workflowApi.listTeacherDraftVersions(run.id);
    setVersions(response.items);
  };

  const save = async (status: TeacherDraftStatus) => {
    if (!draft || content.trim().length < 20) return;
    setBusy(status === 'reviewed' ? 'review' : 'save');
    try {
      const saved = await workflowApi.saveTeacherDraft(run.id, content, status, draft.version);
      setDraft(saved);
      localStorage.removeItem(localDraftKey(run.id));
      setNotice(status === 'reviewed' ? '已标记为教师审核稿，导出将使用此版本' : '教师稿已保存');
      await refreshVersions();
    } catch (reason) { onError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const generate = async () => {
    if (!current) return;
    setBusy('generate');
    try {
      const generated = await workflowApi.generateTeacherSection(
        run.id, current.title, current.content, instruction.trim(),
      );
      const heading = current.content.match(/^#{1,3}\s+.+$/m)?.[0];
      const next = heading && !generated.content.trimStart().startsWith('#')
        ? `${heading}\n\n${generated.content.trim()}` : generated.content;
      updateCurrent(next);
      setInstruction('');
      setMode('edit');
      setNotice('当前资料已生成新版本，确认后请保存');
    } catch (reason) { onError(getErrorMessage(reason)); }
    finally { setBusy(null); }
  };

  const restore = (version: TeacherDraftVersion) => {
    const restored = splitSections(version.content);
    setSections(restored);
    setSelectedId(restored[0]?.id || 'overview');
    setMode('edit');
    setHistoryOpen(false);
    setNotice(`版本 ${version.version} 已恢复到编辑区，保存后将生成新版本`);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch { onError('无法访问剪贴板，请使用 Markdown 导出。'); }
  };

  if (loading) return <div className="materials-loading"><Loader2 className="spin" size={18} /><span>正在准备教师资料</span></div>;
  if (!draft || !current) return <div className="empty-state tall"><FileText size={21} /><strong>教师资料暂不可用</strong></div>;

  return (
    <div className="teacher-materials">
      <header className="materials-toolbar">
        <div className="materials-status">
          {draft.status === 'reviewed' ? <CheckCircle2 size={15} /> : <Pencil size={15} />}
          <div><strong>{draftLabel}</strong><span>版本 {draft.version || '初始'} · {draft.source === 'generated' ? '智能体原稿' : formatTime(draft.updated_at)}</span></div>
        </div>
        <div className="materials-actions">
          <button type="button" title="复制完整教师稿" aria-label="复制完整教师稿" onClick={() => void copy()}>{copied ? <Check size={15} /> : <Copy size={15} />}</button>
          <button type="button" title="版本历史" aria-label="版本历史" className={historyOpen ? 'active' : ''} onClick={() => setHistoryOpen((value) => !value)}><History size={15} /></button>
          <button type="button" onClick={() => onExport('md', 'teacher')}><Download size={14} />Markdown</button>
          <button type="button" onClick={() => onExport('pdf', 'teacher')}><FileDown size={14} />PDF</button>
        </div>
      </header>

      {notice && <div className="materials-notice" role="status"><CheckCircle2 size={14} /><span>{notice}</span></div>}

      {historyOpen && (
        <section className="materials-history" aria-label="教师稿版本历史">
          <header><strong>版本历史</strong><span>恢复后不会覆盖原版本</span></header>
          {versions.length === 0 ? <p>保存一次后，这里会记录可恢复版本。</p> : versions.map((version) => (
            <div key={version.version}>
              <span>版本 {version.version}</span><small>{version.status === 'reviewed' ? '已审核' : '编辑稿'} · {formatTime(version.created_at)}</small>
              <button type="button" onClick={() => restore(version)}><RotateCcw size={13} />恢复到编辑区</button>
            </div>
          ))}
        </section>
      )}

      <div className="materials-main">
        <nav className="materials-nav" aria-label="教师资料目录">
          {sections.map((section, index) => (
            <button key={section.id} type="button" className={section.id === current.id ? 'active' : ''} onClick={() => setSelectedId(section.id)}>
              <span>{index + 1}</span><strong>{section.title}</strong>
            </button>
          ))}
        </nav>

        <section className="materials-canvas">
          <header className="canvas-heading">
            <div><span>当前资料</span><h3>{current.title}</h3></div>
            <div className="mode-switch" aria-label="查看方式">
              <button type="button" className={mode === 'preview' ? 'active' : ''} onClick={() => setMode('preview')}><FileText size={13} />预览</button>
              <button type="button" className={mode === 'edit' ? 'active' : ''} onClick={() => setMode('edit')}><Pencil size={13} />编辑</button>
            </div>
          </header>
          {mode === 'preview' ? (
            <div className="materials-preview"><Markdown>{current.content}</Markdown></div>
          ) : (
            <label className="materials-editor"><span>Markdown 内容</span><textarea value={current.content} onChange={(event) => updateCurrent(event.target.value)} spellCheck rows={18} /></label>
          )}
          <div className="generation-box">
            <label><span>本节修改要求</span><textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} rows={2} placeholder="例如：压缩到 500 字；补充教材中的公式条件；改成表格便于备课" /></label>
            <button type="button" disabled={busy !== null} onClick={() => void generate()}>{busy === 'generate' ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />}生成当前资料</button>
          </div>
        </section>
      </div>

      <footer className="materials-footer">
        <div><Clock3 size={13} /><span>{dirty ? '修改已保存在本机，尚未写入版本历史' : '当前内容已保存'}</span></div>
        <button type="button" disabled={!dirty || busy !== null} onClick={() => void save('draft')}>{busy === 'save' ? <Loader2 className="spin" size={14} /> : <Save size={14} />}保存教师稿</button>
        <button type="button" className="review-button" disabled={busy !== null || (!dirty && draft.status === 'reviewed')} onClick={() => void save('reviewed')}>{busy === 'review' ? <Loader2 className="spin" size={14} /> : <CheckCircle2 size={14} />}标记已审核</button>
      </footer>
    </div>
  );
}
