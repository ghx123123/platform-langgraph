import { CheckCircle2, CheckSquare, Clock3, ListTree, SlidersHorizontal } from 'lucide-react';
import type { KnowledgePoint, TeachingDepth, TeachingScope } from '../types/workflow';
import './TeachingScopePlanner.css';

interface Props {
  points: KnowledgePoint[];
  scope: TeachingScope;
  onChange: (scope: TeachingScope) => void;
  confirmed: boolean;
  onConfirm: () => void;
}

const depthOptions: Array<{ value: TeachingDepth; label: string; hint: string }> = [
  { value: 'overview', label: '概览', hint: '建立结构' },
  { value: 'standard', label: '标准', hint: '讲清并能应用' },
  { value: 'deep', label: '深入', hint: '聚焦难点与迁移' },
];

export function TeachingScopePlanner({ points, scope, onChange, confirmed, onConfirm }: Props) {
  const selected = new Set(scope.selected_point_titles);
  const updateTitles = (titles: string[]) => onChange({ ...scope, selected_point_titles: titles });
  const toggle = (title: string) => {
    updateTitles(selected.has(title) ? scope.selected_point_titles.filter((item) => item !== title) : [...scope.selected_point_titles, title]);
  };
  const selectKey = () => updateTitles(points.filter((item) => item.is_key_point).map((item) => item.title));

  return (
    <section className="scope-planner" aria-label="教学范围与课时设置">
      <header className="scope-heading">
        <div><ListTree size={15} /><h3>教学范围</h3><span>{scope.selected_point_titles.length}/{points.length}</span></div>
        <p>先确认本次要打磨的内容；后续各轮将固定围绕此范围优化，而非顺延讲新章节。</p>
      </header>
      <div className="scope-quick-actions">
        <button type="button" onClick={() => updateTitles(points.map((item) => item.title))}>全选</button>
        <button type="button" onClick={selectKey}>只选重点</button>
        <button type="button" onClick={() => updateTitles([])}>清空</button>
      </div>
      <div className="scope-points">
        {points.map((point) => (
          <label key={point.title} className={selected.has(point.title) ? 'selected' : ''}>
            <input type="checkbox" checked={selected.has(point.title)} onChange={() => toggle(point.title)} />
            <CheckSquare size={13} /><span>{point.title}</span>{point.is_key_point && <em>重点</em>}
          </label>
        ))}
      </div>
      <div className="scope-time">
        <div><label htmlFor="lesson-minutes"><Clock3 size={13} />预计课时</label><strong>{scope.estimated_minutes} 分钟</strong></div>
        <input id="lesson-minutes" type="range" min="10" max="180" step="5" value={scope.estimated_minutes} onChange={(event) => onChange({ ...scope, estimated_minutes: Number(event.target.value) })} />
        <div className="scope-ticks"><span>10</span><span>45</span><span>90</span><span>180</span></div>
      </div>
      <div className="scope-depth">
        <span><SlidersHorizontal size={13} />讲解深度</span>
        <div>{depthOptions.map((option) => <button key={option.value} type="button" className={scope.depth === option.value ? 'active' : ''} onClick={() => onChange({ ...scope, depth: option.value })}><strong>{option.label}</strong><small>{option.hint}</small></button>)}</div>
      </div>
      <div className={`scope-confirmation ${confirmed ? 'confirmed' : ''}`}>
        <span><strong>{scope.selected_point_titles.length} 个知识点</strong><small>{scope.estimated_minutes} 分钟 · {depthOptions.find((item) => item.value === scope.depth)?.label || '标准'}讲解</small></span>
        <button type="button" disabled={scope.selected_point_titles.length === 0} onClick={onConfirm}>{confirmed ? <CheckCircle2 size={14} /> : <CheckSquare size={14} />}{confirmed ? '范围已确认' : '确认本次范围'}</button>
      </div>
    </section>
  );
}
