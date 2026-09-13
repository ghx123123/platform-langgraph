// SessionRunCard.tsx - 教学会话卡片：状态、综合评分、轮次、两步删除确认
import { useEffect, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { AlertTriangle, Award, Clock3, Trash2 } from 'lucide-react';
import type { RunStatus, WorkflowRun } from '../types/workflow';
import './SessionRunCard.css';

/** 状态中文名 */
const STATUS_TEXT: Record<RunStatus, string> = {
  queued: '正在启动',
  running: '教学进行中',
  paused: '等待你处理',
  completed: '已完成',
  failed: '运行失败',
  cancelled: '已停止',
};

const pad2 = (n: number): string => String(n).padStart(2, '0');

/** 运行中会话超过这个时长没有更新, 视为停滞(实测桥崩溃后 run 会永远停在 running)。 */
const STALL_THRESHOLD_MS = 10 * 60 * 1000;

/** 返回停滞描述(如「已 2 小时无进展」), 未停滞返回空串。 */
function stalledLabel(run: WorkflowRun): string {
  if (run.status !== 'running' && run.status !== 'queued') return '';
  const ts = Date.parse(run.updated_at || run.created_at);
  if (Number.isNaN(ts)) return '';
  const idle = Date.now() - ts;
  if (idle < STALL_THRESHOLD_MS) return '';
  const minutes = Math.floor(idle / 60000);
  const text = minutes >= 60 ? `${Math.floor(minutes / 60)} 小时` : `${minutes} 分钟`;
  return `已 ${text}无进展`;
}

/** 格式化创建时间为紧凑的「M月D日 HH:mm」 */
function formatTime(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const d = new Date(ts);
  return `${d.getMonth() + 1}月${d.getDate()}日 ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

interface SessionRunCardProps {
  run: WorkflowRun;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export function SessionRunCard({ run, selected, onSelect, onDelete }: SessionRunCardProps) {
  const [confirming, setConfirming] = useState(false);

  // 切换到其他会话时复位删除确认
  useEffect(() => {
    setConfirming(false);
  }, [run.id]);

  const isCompleted = run.status === 'completed';
  const isPaused = run.status === 'paused';
  const isFailed = run.status === 'failed';
  const score = isCompleted ? run.review?.score : undefined;
  const stalled = stalledLabel(run);

  const currentIteration =
    typeof run.teaching_data.current_iteration === 'number' ? run.teaching_data.current_iteration : 0;
  const maxIterations =
    typeof run.teaching_data.max_iterations === 'number' ? run.teaching_data.max_iterations : 0;
  const roundText =
    maxIterations > 0
      ? `第 ${currentIteration}/${maxIterations} 轮`
      : currentIteration > 0
        ? `共 ${currentIteration} 轮`
        : '';

  const handleSelect = (): void => {
    if (confirming) setConfirming(false);
    onSelect();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    if (event.target !== event.currentTarget) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleSelect();
    }
  };

  const handleDeleteClick = (e: MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    setConfirming(true);
  };

  const handleConfirmDelete = (e: MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    setConfirming(false);
    onDelete();
  };

  const handleCancelDelete = (e: MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    setConfirming(false);
  };

  return (
    <div
      className={`session-card session-status-${run.status}${selected ? ' selected' : ''}${isFailed ? ' is-failed' : ''}${stalled ? ' is-stalled' : ''}`}
      onClick={handleSelect}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${run.objective}，${STATUS_TEXT[run.status]}${stalled ? `，${stalled}` : ''}${selected ? '，当前已选中' : ''}`}
      title={isFailed && run.error ? run.error : stalled ? `${stalled}，可能已中断；可删除后重新启动` : undefined}
    >
      <span className="session-card-dot" aria-hidden="true" />
      <div className="session-card-main">
        <strong className="session-card-title" title={run.objective}>{run.objective}</strong>
        <div className="session-card-meta">
          <Clock3 size={11} aria-hidden="true" />
          <span className="session-card-time">{formatTime(run.created_at)}</span>
          {/* 窄卡片下状态文字会被省略号截断，title 保证完整文案仍可查看 */}
          <span className="session-card-status-text" title={STATUS_TEXT[run.status]}>
            {STATUS_TEXT[run.status]}
          </span>
          {(isFailed || stalled) && <AlertTriangle size={11} aria-hidden="true" />}
        </div>
      </div>
      <div className="session-card-side">
        {typeof score === 'number' && (
          <span className="session-card-score" title="综合评分">
            <Award size={10} aria-hidden="true" />
            综合评分 {score} 分
          </span>
        )}
        {isCompleted && roundText !== '' && (
          <span className="session-card-round">{roundText}</span>
        )}
        {isPaused && <span className="session-card-attention">待你处理</span>}
        {stalled && <span className="session-card-stalled" title="超过 10 分钟没有新进展，可能已中断">{stalled}</span>}
        {confirming ? (
          <span className="session-card-confirm" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="session-card-confirm-danger" onClick={handleConfirmDelete}>
              删除
            </button>
            <button type="button" className="session-card-confirm-cancel" onClick={handleCancelDelete}>
              取消
            </button>
          </span>
        ) : (
          <button type="button" className="session-card-delete" title="删除会话" aria-label="删除会话" onClick={handleDeleteClick}>
            <Trash2 size={13} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}

export default SessionRunCard;
