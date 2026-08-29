import { useEffect, useMemo, useState } from 'react';
import {
  Archive, BookMarked, CheckCircle2, ChevronRight, Copy, ExternalLink, Eye, FileStack,
  FolderOpen, LibraryBig, ListFilter, Loader2, Search, ShieldCheck, Trash2, X,
} from 'lucide-react';
import { documentApi } from '../lib/api';
import type {
  ArchiveMaterialCategory, CourseArchiveDetail, CourseArchiveMaterial,
  CourseArchiveSummary, PrepareArchiveInput,
} from '../types/workflow';
import './CourseArchiveWorkspace.css';

const categoryLabels: Record<ArchiveMaterialCategory, string> = {
  syllabus: '教学大纲', schedule: '教学进度', textbook: '教材', courseware: '课件',
  lesson_plan: '教案设计', experiment: '实验实训', code: '代码', teaching_record: '迭代记录',
  review: '审核评价', interactive: '交互资源', reference: '参考资料', media: '媒体', other: '其他',
};

const primaryPriority: ArchiveMaterialCategory[] = ['textbook', 'courseware', 'lesson_plan', 'syllabus', 'experiment'];
const parseableExtensions = new Set(['.pdf', '.docx', '.pptx', '.md', '.txt', '.xlsx', '.xls', '.csv', '.html', '.htm', '.py', '.json', '.ipynb']);

function isSelectable(item: CourseArchiveMaterial): boolean {
  return item.parse_status !== 'unsupported' && parseableExtensions.has(item.extension.toLowerCase());
}

interface Props {
  summaries: CourseArchiveSummary[];
  archive: CourseArchiveDetail | null;
  loading: boolean;
  importing: boolean;
  preparing: boolean;
  prepareProgress: { done: number; total: number };
  importStatus: string;
  onImport: () => void;
  onSelectArchive: (archiveId: string) => void;
  onDeleteArchive: (archiveId: string) => void;
  onPrepare: (input: PrepareArchiveInput) => void;
}

function pickPrimary(materials: CourseArchiveMaterial[]): string | null {
  const parsed = materials.filter(isSelectable);
  for (const category of primaryPriority) {
    const match = parsed.find((item) => item.category === category);
    if (match) return match.id;
  }
  return parsed[0]?.id || null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function CourseArchiveWorkspace({
  summaries, archive, loading, importing, preparing, prepareProgress, importStatus,
  onImport, onSelectArchive, onDeleteArchive, onPrepare,
}: Props) {
  const [chapter, setChapter] = useState<string>('all');
  const [category, setCategory] = useState<'all' | ArchiveMaterialCategory>('all');
  const [query, setQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [primaryId, setPrimaryId] = useState<string | null>(null);
  const [scheduleId, setScheduleId] = useState('');
  const [copied, setCopied] = useState(false);
  const [previewMaterial, setPreviewMaterial] = useState<CourseArchiveMaterial | null>(null);

  const chooseScope = (nextChapter: string, detail = archive) => {
    setChapter(nextChapter);
    if (!detail) return;
    const scoped = detail.materials.filter((item) => isSelectable(item) && (
      nextChapter === 'all' || item.chapter === nextChapter || ['syllabus', 'schedule'].includes(item.category)
    ));
    setSelectedIds(scoped.map((item) => item.id));
    setPrimaryId(pickPrimary(scoped.filter((item) => nextChapter === 'all' || item.chapter === nextChapter)) || pickPrimary(scoped));
    setScheduleId(detail.schedule.find((item) => nextChapter === 'all' || item.chapter === nextChapter)?.id || '');
  };

  useEffect(() => {
    if (!archive) return;
    chooseScope(archive.chapters[0]?.key || 'all', archive);
    setCategory('all');
    setQuery('');
  }, [archive?.id]);

  const visibleMaterials = useMemo(() => {
    if (!archive) return [];
    const normalized = query.trim().toLowerCase();
    return archive.materials.filter((item) => {
      const inChapter = chapter === 'all' || item.chapter === chapter || ['syllabus', 'schedule'].includes(item.category);
      const inCategory = category === 'all' || item.category === category;
      const matches = !normalized || `${item.name} ${item.path}`.toLowerCase().includes(normalized);
      return inChapter && inCategory && matches;
    });
  }, [archive, category, chapter, query]);

  const availableSchedule = useMemo(() => archive?.schedule.filter((item) => chapter === 'all' || item.chapter === chapter) || [], [archive, chapter]);
  const selectedSchedule = archive?.schedule.find((item) => item.id === scheduleId);
  const selectedMaterials = archive?.materials.filter((item) => selectedIds.includes(item.id)) || [];
  const selectedUsableCount = selectedIds.filter((id) => {
    const item = archive?.materials.find((candidate) => candidate.id === id);
    return !!item && isSelectable(item);
  }).length;
  const toggleMaterial = (item: CourseArchiveMaterial) => {
    if (!isSelectable(item)) return;
    setSelectedIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id]);
    if (!selectedIds.includes(item.id) && !primaryId) setPrimaryId(item.id);
    if (selectedIds.includes(item.id) && primaryId === item.id) {
      const remaining = archive?.materials.filter((candidate) => candidate.id !== item.id && selectedIds.includes(candidate.id) && isSelectable(candidate)) || [];
      setPrimaryId(pickPrimary(remaining));
    }
  };

  if (loading && !archive) {
    return <div className="archive-loading"><Loader2 className="spin" size={22} /><strong>正在读取学期资料库</strong></div>;
  }

  if (!archive) {
    return (
      <div className="archive-empty">
        <div className="archive-empty-icon"><LibraryBig size={25} /></div>
        <h2>建立学期资料库</h2>
        <p>先在课程目录导入文件、文件夹或关联本地路径，再回到这里为当前讲次选择教材、课件、教案与历史改进记录。</p>
        <button type="button" className="primary-button compact" onClick={onImport} disabled={importing}>
          {importing ? <Loader2 className="spin" size={15} /> : <FolderOpen size={15} />}{importing ? importStatus : '前往课程目录导入'}
        </button>
      </div>
    );
  }

  const selectedSet = new Set(selectedIds);
  return (
    <div className="archive-workspace">
      <header className="archive-toolbar">
        <div className="archive-identity"><Archive size={19} /><div><span>学期资料库</span><strong>{archive.course_title}</strong><small>{archive.name}</small></div></div>
        <div className="archive-metrics">
          <span><strong>{archive.total_files}</strong><small>资料</small></span>
          <span><strong>{archive.chapter_count}</strong><small>章节</small></span>
          <span><strong>{archive.parsed_files}</strong><small>已读正文</small></span>
          <span><strong>{archive.duplicate_groups}</strong><small>重复组</small></span>
        </div>
        <button type="button" className="secondary-button archive-import" onClick={onImport} disabled={importing}>{importing ? <Loader2 className="spin" size={14} /> : <FolderOpen size={14} />}{importing ? importStatus : '前往课程目录导入'}</button>
      </header>

      <div className="archive-columns">
        <aside className="archive-navigation">
          <div className="archive-section-heading"><span>课程资料库</span><small>{summaries.length}</small></div>
          {summaries.length > 1 && <select value={archive.id} onChange={(event) => onSelectArchive(event.target.value)} aria-label="切换学期资料库">{summaries.map((item) => <option value={item.id} key={item.id}>{item.course_title}</option>)}</select>}
          <div className="archive-section-heading"><span>章节导航</span><small>{archive.chapters.length}</small></div>
          <nav className="archive-chapters" aria-label="课程章节">
            <button type="button" className={chapter === 'all' ? 'active' : ''} onClick={() => chooseScope('all')}><FileStack size={14} /><span>全部资料</span><small>{archive.total_files}</small><ChevronRight size={13} /></button>
            {archive.chapters.map((item) => <button type="button" key={item.key} className={chapter === item.key ? 'active' : ''} onClick={() => chooseScope(item.key)}><BookMarked size={14} /><span>{item.label}</span><small>{item.material_count}</small><ChevronRight size={13} /></button>)}
          </nav>
          <div className="archive-category-summary">
            <div className="archive-section-heading"><span>资料构成</span></div>
            {Object.entries(archive.categories).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([key, count]) => <div key={key}><span>{categoryLabels[key as ArchiveMaterialCategory] || key}</span><strong>{count}</strong></div>)}
          </div>
          <button type="button" className="archive-delete" onClick={() => onDeleteArchive(archive.id)}><Trash2 size={13} />删除当前资料库</button>
        </aside>

        <main className="archive-resources">
          <div className="archive-resource-head">
            <div><span>当前范围</span><h2>{chapter === 'all' ? '全部课程资料' : chapter}</h2><p>勾选本讲次要使用的材料。已索引文件会在确认后才导入原件并提取正文。</p></div>
            <label className="archive-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文件名或路径" /></label>
          </div>
          <div className="archive-filters" aria-label="资料类型筛选">
            <ListFilter size={13} />
            <button type="button" className={category === 'all' ? 'active' : ''} onClick={() => setCategory('all')}>全部</button>
            {(Object.keys(archive.categories) as ArchiveMaterialCategory[]).filter((key) => archive.categories[key]).map((key) => <button type="button" key={key} className={category === key ? 'active' : ''} onClick={() => setCategory(key)}>{categoryLabels[key]}<small>{archive.categories[key]}</small></button>)}
          </div>
          {availableSchedule.length > 0 && <label className="archive-session-select"><span>当前讲次</span><select value={scheduleId} onChange={(event) => setScheduleId(event.target.value)}><option value="">不绑定进度表讲次</option>{availableSchedule.map((item) => <option value={item.id} key={item.id}>{item.label} · {item.content}</option>)}</select></label>}
          <div className="archive-table" role="table" aria-label="教学资料矩阵">
            <div className="archive-table-header" role="row"><span>使用</span><span>主材料</span><span>资料与用途</span><span>状态</span><span>查看</span></div>
            <div className="archive-table-body">
              {visibleMaterials.length === 0 ? <div className="archive-no-results">当前筛选下没有资料</div> : visibleMaterials.map((item) => {
                const parsed = item.parse_status === 'parsed';
                const usable = isSelectable(item);
                const selected = selectedSet.has(item.id);
                return <div className={`archive-material-row ${selected ? 'selected' : ''}`} role="row" key={item.id}>
                  <label className="archive-use" title={usable ? '纳入当前讲次备课包；进入下一步时按需提取' : item.parse_message}><input type="checkbox" checked={selected} disabled={!usable} onChange={() => toggleMaterial(item)} /><span /></label>
                  <label className="archive-primary" title={usable ? '设为主材料' : '该文件暂不支持正文提取'}><input type="radio" name="primary-material" checked={primaryId === item.id} disabled={!usable || !selected} onChange={() => setPrimaryId(item.id)} /><span /></label>
                  <div className="archive-material-copy"><div><strong>{item.name}</strong>{item.version && <em>{item.version}</em>}{item.duplicate_group && <em className="duplicate">重复</em>}</div><span>{categoryLabels[item.category]}{item.chapter ? ` · ${item.chapter}` : ''}{item.lesson ? ` · ${item.lesson}` : ''} · {formatSize(item.size)}</span><small title={item.path}>{item.path}</small></div>
                  <div className={`archive-parse-status status-${item.parse_status}`}><i />{parsed ? `${item.character_count.toLocaleString()} 字` : item.parse_status === 'metadata_only' ? item.document_id ? '待按需提取' : '已索引' : item.parse_status === 'parse_failed' ? '可重新提取' : '仅原文件'}</div>
                  <div className="archive-open">{item.document_id && <><button type="button" onClick={() => setPreviewMaterial(item)} title="在页面内预览" aria-label={`在页面内预览${item.name}`}><Eye size={14} /></button><button type="button" onClick={() => window.open(documentApi.originalUrl(item.document_id!), '_blank', 'noopener,noreferrer')} title="新窗口打开原文件" aria-label={`新窗口打开${item.name}`}><ExternalLink size={14} /></button></>}</div>
                </div>;
              })}
            </div>
          </div>
          {selectedMaterials.length > 0 && <section className="archive-selected-tray" aria-label="已选备课资料"><div><CheckCircle2 size={14} /><strong>已选资料</strong><span>{selectedMaterials.length} 份</span><button type="button" onClick={() => { setSelectedIds([]); setPrimaryId(null); }}>清空</button></div><div>{selectedMaterials.map((item) => <span key={item.id} className={primaryId === item.id ? 'primary' : ''} title={item.name}>{primaryId === item.id && <em>主</em>}<strong>{item.name}</strong><button type="button" onClick={() => toggleMaterial(item)} aria-label={`移除${item.name}`}><X size={11} /></button></span>)}</div></section>}
          <footer className="archive-pack-bar"><div><strong>当前讲次备课包</strong><span>已选 {selectedUsableCount} 份材料{primaryId ? '，主材料已确定' : '，请指定主材料'}；下一步仅导入并提取所选内容</span>{preparing && prepareProgress.total > 0 && <progress max={prepareProgress.total} value={prepareProgress.done} aria-label="所选原件导入进度" />}</div><button type="button" className="primary-button compact" disabled={preparing || !primaryId || selectedUsableCount === 0} onClick={() => onPrepare({ chapter: chapter === 'all' ? null : chapter, schedule_id: scheduleId || null, session_label: selectedSchedule?.content || null, material_ids: selectedIds, primary_material_id: primaryId })}>{preparing ? <Loader2 className="spin" size={15} /> : <ChevronRight size={15} />}{preparing ? prepareProgress.total > 0 ? `正在导入 ${prepareProgress.done} / ${prepareProgress.total}` : '正在按需提取' : '确认资料并进入课程设计'}</button></footer>
        </main>

        <aside className="archive-habits">
          <div className="archive-habits-head"><div><ShieldCheck size={15} /><span>历史备课习惯</span><small>{archive.habits.length} 条</small></div><button type="button" onClick={() => void navigator.clipboard.writeText(archive.preparation_profile_prompt).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1400); })} title="复制可复用备课经验">{copied ? <CheckCircle2 size={13} /> : <Copy size={13} />}{copied ? '已复制' : '复制经验'}</button></div>
          <p className="archive-habits-intro">系统只把有文件或正文证据的做法凝练为规则，并自动加入后续教学设计上下文。</p>
          <div className="archive-habit-list">{archive.habits.map((habit, index) => <details key={habit.key} open={index < 3}><summary><span>{index + 1}</span><div><strong>{habit.title}</strong><small>证据置信度 {Math.round(habit.confidence * 100)}%</small></div><ChevronRight size={13} /></summary><p>{habit.description}</p><div className="archive-habit-rule">{habit.reusable_instruction}</div><ul>{habit.evidence.map((item) => <li key={item} title={item}>{item}</li>)}</ul></details>)}</div>
          {archive.warnings.length > 0 && <details className="archive-warnings"><summary>查看 {archive.warnings.length} 个解析提示</summary><ul>{archive.warnings.map((item) => <li key={item}>{item}</li>)}</ul></details>}
        </aside>
      </div>
      {previewMaterial?.document_id && <aside className="archive-preview-drawer" aria-label="资料原页预览"><header><div><span>{categoryLabels[previewMaterial.category]}</span><strong>{previewMaterial.name}</strong><small>{previewMaterial.path}</small></div><button type="button" onClick={() => setPreviewMaterial(null)} aria-label="关闭预览"><X size={16} /></button></header><div>{previewMaterial.preview_available ? <iframe title={`${previewMaterial.name}原页预览`} src={documentApi.previewUrl(previewMaterial.document_id)} /> : <div className="archive-preview-unavailable"><FileStack size={24} /><strong>该格式暂不支持页面内预览</strong><span>可在新窗口中打开原文件。</span></div>}</div><footer><button type="button" onClick={() => window.open(documentApi.originalUrl(previewMaterial.document_id!), '_blank', 'noopener,noreferrer')}><ExternalLink size={14} />打开原文件</button>{previewMaterial.parse_status !== 'unsupported' && <button type="button" className="primary-button compact" onClick={() => { if (!selectedIds.includes(previewMaterial.id)) toggleMaterial(previewMaterial); setPreviewMaterial(null); }}><CheckCircle2 size={14} />{selectedIds.includes(previewMaterial.id) ? '已在备课包中' : '加入备课包'}</button>}</footer></aside>}
    </div>
  );
}
