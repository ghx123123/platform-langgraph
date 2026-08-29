import { useCallback, useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  ArrowRight, ArrowUpRight, BadgeCheck, Database, FileCheck2, Files, LibraryBig,
  Loader2, PackageCheck, PanelsTopLeft, RefreshCw, Sparkles,
} from 'lucide-react';
import { dataHubApi, getErrorMessage } from '../lib/api';
import type { CompositionSummary, CourseArchiveSummary, CourseDesignSummary, DataHubCatalog, WorkflowRun } from '../types/workflow';
import './DataHubDashboard.css';

type DashboardTarget = 'hub' | 'materials' | 'design' | 'exports';

interface Props {
  archives: CourseArchiveSummary[];
  designs: CourseDesignSummary[];
  runs: WorkflowRun[];
  onNavigate: (target: DashboardTarget) => void;
}

const targetMeta = {
  hub: { label: '课程资料库', detail: '本地目录与原始资料', color: '#2f7bea', soft: '#eaf3ff', icon: LibraryBig },
  materials: { label: '资料单元', detail: '按讲次组织的备课包', color: '#18a875', soft: '#e8f8f1', icon: Database },
  design: { label: '课程设计', detail: '生成、讨论与多轮打磨', color: '#e66f36', soft: '#fff0e8', icon: PanelsTopLeft },
  exports: { label: '成果中心', detail: '教案、资料包与导出文件', color: '#8a5c82', soft: '#f4eaf1', icon: FileCheck2 },
} as const;

function relativeDate(value: string): string {
  const time = new Date(value).getTime();
  if (!Number.isFinite(time)) return '';
  const days = Math.floor((Date.now() - time) / 86_400_000);
  if (days <= 0) return '今天';
  if (days === 1) return '昨天';
  if (days < 7) return `${days} 天前`;
  return new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

export function DataHubDashboard({ archives, designs, runs, onNavigate }: Props) {
  const [catalog, setCatalog] = useState<DataHubCatalog | null>(null);
  const [compositions, setCompositions] = useState<CompositionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [focus, setFocus] = useState<DashboardTarget>('hub');
  const [period, setPeriod] = useState<'term' | 'month' | 'week'>('term');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [catalogResult, compositionResult] = await Promise.all([
        dataHubApi.catalog({ summary_only: true }),
        dataHubApi.listCompositions(),
      ]);
      setCatalog(catalogResult);
      setCompositions(compositionResult.items);
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const totals = useMemo(() => {
    const materials = archives.reduce((sum, archive) => sum + archive.total_files, 0);
    const units = catalog?.stats.units ?? catalog?.units.length ?? 0;
    const reviewed = designs.filter((design) => design.status === 'reviewed').length;
    const activeRuns = runs.filter((run) => ['queued', 'running', 'paused'].includes(run.status)).length;
    const exported = designs.reduce((total, item) => total + (item.export_count || 0), 0);
    return { materials, units, reviewed, activeRuns, outputs: compositions.length + exported };
  }, [archives, catalog, compositions.length, designs, runs]);

  const cards = [
    { key: 'hub' as const, value: archives.length, unit: '个课程目录', note: `${totals.materials} 份原始文件` },
    { key: 'materials' as const, value: totals.units, unit: '个资料单元', note: `${catalog?.stats.generated_blocks || 0} 条生成内容` },
    { key: 'design' as const, value: designs.length, unit: '份设计稿', note: `${totals.activeRuns} 个任务进行中` },
    { key: 'exports' as const, value: totals.outputs, unit: '项可用成果', note: `${totals.reviewed} 份教案可定稿` },
  ];

  const totalAssets = totals.materials + totals.units + designs.length + totals.outputs;
  const distribution = cards.map((card) => ({ ...card, ratio: totalAssets ? Math.max(3, Math.round((card.key === 'hub' ? totals.materials : card.value) / totalAssets * 100)) : 0 }));
  const flow = [
    { key: 'hub' as const, value: totals.materials, label: '份文件', icon: Files },
    { key: 'materials' as const, value: totals.units, label: '个单元', icon: PackageCheck },
    { key: 'design' as const, value: designs.length, label: '份设计', icon: Sparkles },
    { key: 'exports' as const, value: totals.outputs, label: '项成果', icon: BadgeCheck },
  ];
  const recent = useMemo(() => [
    ...archives.map((item) => ({ id: `a-${item.id}`, target: 'hub' as const, title: item.name, detail: `${item.total_files} 份文件 · 课程资料库`, updated_at: item.updated_at })),
    ...designs.map((item) => ({ id: `d-${item.id}`, target: 'design' as const, title: item.title, detail: `第 ${item.version} 版 · 课程设计`, updated_at: item.updated_at })),
    ...compositions.map((item) => ({ id: `c-${item.id}`, target: 'exports' as const, title: item.title, detail: `${item.block_count} 个内容块 · 成果中心`, updated_at: item.updated_at })),
  ].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5), [archives, compositions, designs]);

  const pending = [
    { target: 'design' as const, value: designs.filter((item) => item.status === 'draft').length, text: '份课程设计等待教师确认' },
    { target: 'design' as const, value: runs.filter((item) => item.status === 'paused').length, text: '个生成任务等待教师参与' },
  ].filter((item) => item.value > 0);

  const focused = targetMeta[focus];
  return (
    <main className="data-dashboard">
      <header className="dashboard-heading">
        <div><span>跨课程数据总览</span><h1>教学资产，一屏掌握</h1><p>从原始资料到可交付成果，查看四个同级模块的数据状态与流转关系。</p></div>
        <button type="button" onClick={() => void refresh()} disabled={loading}><RefreshCw className={loading ? 'spin' : ''} size={15} />刷新数据</button>
      </header>

      {error && <div className="dashboard-error">{error}<button type="button" onClick={() => void refresh()}>重试</button></div>}
      <section className="dashboard-modules" aria-label="四个业务模块">
        {cards.map((card) => {
          const meta = targetMeta[card.key]; const Icon = meta.icon;
          return <button type="button" key={card.key} className={focus === card.key ? 'active' : ''} style={{ '--module-color': meta.color, '--module-soft': meta.soft } as CSSProperties} onClick={() => onNavigate(card.key)} aria-label={`进入${meta.label}`}>
            <span className="dashboard-module-icon"><Icon size={17} /></span><span className="dashboard-module-name"><strong>{meta.label}</strong><small>{meta.detail}</small></span><span className="dashboard-module-enter">进入<ArrowUpRight size={14} /></span>
            <span className="dashboard-module-value"><b>{loading ? <Loader2 className="spin" size={20} /> : card.value.toLocaleString()}</b><em>{card.unit}</em></span><small className="dashboard-module-note">{card.note}</small>
          </button>;
        })}
      </section>

      <div className="dashboard-grid">
        <div className="dashboard-primary">
          <section className="dashboard-panel dashboard-flow-panel">
            <header><div><strong>教学资料流转</strong><small>点击节点进入对应业务模块</small></div><div className="dashboard-period">{(['term', 'month', 'week'] as const).map((key) => <button type="button" key={key} className={period === key ? 'active' : ''} onClick={() => setPeriod(key)}>{{ term: '本学期', month: '本月', week: '本周' }[key]}</button>)}</div></header>
            <div className="dashboard-flow">{flow.map((item, index) => { const meta = targetMeta[item.key]; const Icon = item.icon; return <div className="dashboard-flow-part" key={item.key}>{index > 0 && <span className="dashboard-flow-line"><ArrowRight size={15} /></span>}<button type="button" style={{ '--module-color': meta.color, '--module-soft': meta.soft } as CSSProperties} onClick={() => onNavigate(item.key)}><span><Icon size={20} /></span><b>{item.value.toLocaleString()} {item.label}</b><small>{meta.label}</small></button></div>; })}</div>
          </section>

          <div className="dashboard-lower">
            <section className="dashboard-panel dashboard-distribution"><header><div><strong>教学资产分布</strong><small>所有数字均来自当前平台数据</small></div><b>{totalAssets.toLocaleString()}</b></header><div>{distribution.map((item) => { const meta = targetMeta[item.key]; return <button type="button" key={item.key} onClick={() => setFocus(item.key)}><span><i style={{ background: meta.color }} />{meta.label}<b>{item.key === 'hub' ? totals.materials : item.value}</b></span><span className="distribution-track"><i style={{ width: `${item.ratio}%`, background: meta.color }} /></span></button>; })}</div></section>
            <section className="dashboard-panel dashboard-recent"><header><div><strong>最近更新</strong><small>跨模块查看最近数据变化</small></div></header><div>{recent.length ? recent.map((item) => <button type="button" key={item.id} onClick={() => onNavigate(item.target)}><span style={{ background: targetMeta[item.target].soft, color: targetMeta[item.target].color }}>{item.target === 'hub' ? <Files size={13} /> : item.target === 'design' ? <PanelsTopLeft size={13} /> : <FileCheck2 size={13} />}</span><span><strong>{item.title}</strong><small>{item.detail}</small></span><time>{relativeDate(item.updated_at)}</time></button>) : <p>还没有更新记录</p>}</div></section>
          </div>
        </div>

        <aside className="dashboard-panel dashboard-tasks">
          <header><div><strong>需要处理</strong><small>跨模块聚合待办事项</small></div><b>{pending.reduce((sum, item) => sum + item.value, 0)}</b></header>
          <div className="dashboard-task-list">{pending.length ? pending.map((item) => <button type="button" key={item.target} onClick={() => onNavigate(item.target)} style={{ '--module-color': targetMeta[item.target].color } as CSSProperties}><i /><span><strong>{item.value} {item.text}</strong><small>点击进入{targetMeta[item.target].label}处理</small></span><ArrowRight size={14} /></button>) : <p><BadgeCheck size={18} />当前没有待处理事项</p>}</div>
          <section className="dashboard-focus"><span>当前聚焦模块</span><strong>{focused.label}</strong><p>{focused.detail}。进入模块可查看明细、编辑数据或继续当前工作。</p><button type="button" onClick={() => onNavigate(focus)}>进入模块<ArrowUpRight size={13} /></button></section>
        </aside>
      </div>
    </main>
  );
}
