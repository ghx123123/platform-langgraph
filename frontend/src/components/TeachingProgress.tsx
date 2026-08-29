// TeachingProgress.tsx - 教学进度：轮次 + 真实运行时长（每秒刷新）
import { useEffect, useMemo, useState } from 'react';
import { Clock3, Repeat } from 'lucide-react';
import type { RunStatus, WorkflowRun } from '../types/workflow';
import './TeachingProgress.css';

/** 需要持续计时的状态；终态（completed/failed/cancelled）定格不再跳动 */
const LIVE_STATUSES: RunStatus[] = ['queued', 'running'];

/** 按「X分Y秒」格式化时长 */
function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}分${rest}秒`;
}

interface TeachingProgressProps {
  run: WorkflowRun;
  currentNode?: string;
  currentIteration?: number;
}

export function TeachingProgress({ run, currentIteration }: TeachingProgressProps) {
  const isLive = LIVE_STATUSES.includes(run.status);
  const [now, setNow] = useState(() => Date.now());

  // 仅在 queued/running/paused 时每秒刷新；组件卸载时清理 interval
  useEffect(() => {
    if (!isLive) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [isLive]);

  const elapsedSeconds = useMemo(() => {
    const start = Date.parse(run.created_at);
    if (Number.isNaN(start)) return 0;
    // Paused sessions must stay frozen at their last persisted update. Counting
    // wall-clock time while waiting for teacher input produces multi-day ETAs
    // when an old session is restored.
    const end = isLive ? now : Date.parse(run.updated_at);
    const endMs = Number.isNaN(end) ? start : end;
    return Math.max(0, (endMs - start) / 1000);
  }, [isLive, now, run.created_at, run.updated_at]);

  const roundText = useMemo(() => {
    const current = typeof currentIteration === 'number'
      ? currentIteration
      : typeof run.teaching_data.current_iteration === 'number' ? run.teaching_data.current_iteration : 0;
    const max =
      typeof run.teaching_data.max_iterations === 'number' ? run.teaching_data.max_iterations : 0;
    if (max > 0) return `第 ${current}/${max} 轮`;
    return current > 0 ? `共 ${current} 轮` : '共 0 轮';
  }, [currentIteration, run.teaching_data.current_iteration, run.teaching_data.max_iterations]);

  const isPaused = run.status === 'paused';
  const elapsedText = formatDuration(elapsedSeconds);

  return (
    <div className="progress-chips" aria-label="教学进度">
      <span className="progress-chip">
        <Repeat size={12} aria-hidden="true" />
        {roundText}
      </span>
      <span className={`progress-chip${isPaused ? ' is-paused' : ''}`}>
        <Clock3 size={12} aria-hidden="true" />
        {isPaused ? `已暂停 · 已运行 ${elapsedText}` : `已运行 ${elapsedText}`}
      </span>
    </div>
  );
}

export default TeachingProgress;
