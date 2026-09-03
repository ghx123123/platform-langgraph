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
      className={`session-card session-status-${run.status}${selected ? ' selected' : ''}${isFailed ? ' is-failed' : ''}`}
      onClick={handleSelect}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${run.objective}，${STATUS_TEXT[run.status]}${selected ? '，当前已选中' : ''}`}
      title={isFailed && run.error ? run.error : undefined}
    >
      <span className="session-card-dot" aria-hidden="true" />
      <div className="session-card-main">
        <strong className="session-card-title">{run.objective}</strong>
        <div className="session-card-meta">
          <Clock3 size={11} aria-hidden="true" />
          <span className="session-card-time">{formatTime(run.created_at)}</span>
          <span className="session-card-status-text">{STATUS_TEXT[run.status]}</span>
          {isFailed && <AlertTriangle size={11} aria-hidden="true" />}
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
