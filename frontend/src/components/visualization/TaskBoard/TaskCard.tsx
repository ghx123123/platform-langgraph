import { cn } from '../../../utils/cn';
import type { TaskExecution } from '../../../types/visualization';

const STATUS_CONFIG = {
  queued: {
    label: '排队中',
    icon: '⏳',
    bg: 'bg-slate-100',
    border: 'border-slate-300',
    text: 'text-slate-600',
  },
  running: {
    label: '运行中',
    icon: '🔄',
    bg: 'bg-blue-100',
    border: 'border-blue-300',
    text: 'text-blue-600',
  },
  completed: {
    label: '已完成',
    icon: '✅',
    bg: 'bg-emerald-100',
    border: 'border-emerald-300',
    text: 'text-emerald-600',
  },
  failed: {
    label: '失败',
    icon: '❌',
    bg: 'bg-red-100',
    border: 'border-red-300',
    text: 'text-red-600',
  },
  cancelled: {
    label: '已取消',
    icon: '🚫',
    bg: 'bg-slate-100',
    border: 'border-slate-300',
    text: 'text-slate-400',
  },
};

const PRIORITY_CONFIG = {
  low: { label: '低', bg: 'bg-slate-100 text-slate-500' },
  medium: { label: '中', bg: 'bg-blue-100 text-blue-600' },
  high: { label: '高', bg: 'bg-amber-100 text-amber-600' },
  critical: { label: '紧急', bg: 'bg-red-100 text-red-600' },
};

interface TaskCardProps {
  task: TaskExecution;
  onClick?: (task: TaskExecution) => void;
  compact?: boolean;
}

export function TaskCard({ task, onClick, compact = false }: TaskCardProps) {
  const statusConfig = STATUS_CONFIG[task.status];
  const priorityConfig = PRIORITY_CONFIG[task.priority];

  return (
    <div
      className={cn(
        'bg-white rounded-xl border shadow-sm transition-all duration-200 cursor-pointer hover:shadow-md',
        statusConfig.border,
        onClick && 'hover:scale-[1.02]'
      )}
      onClick={() => onClick?.(task)}
    >
      <div className="p-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-sm text-slate-800 truncate">{task.title}</h4>
            {task.description && !compact && (
              <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{task.description}</p>
            )}
          </div>
          <span
            className={cn(
              'px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0',
              priorityConfig.bg
            )}
          >
            {priorityConfig.label}
          </span>
        </div>

        {/* Status and Progress */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span>{statusConfig.icon}</span>
            <span className={cn('text-xs font-medium', statusConfig.text)}>
              {statusConfig.label}
            </span>
          </div>

          {task.assignedAgent && !compact && (
            <div className="text-xs text-slate-400 truncate">
              → {task.assignedAgent}
            </div>
          )}
        </div>

        {/* Progress bar for running tasks */}
        {task.status === 'running' && (
          <div className="mt-2">
            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full transition-all duration-300"
                style={{ width: `${task.progress}%` }}
              />
            </div>
            <div className="text-xs text-slate-400 mt-1 text-right">{task.progress}%</div>
          </div>
        )}

        {/* Time info */}
        {!compact && (
          <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
            <span>创建: {formatTime(task.createdAt)}</span>
            {task.completedAt && (
              <span className="text-emerald-500">完成: {formatTime(task.completedAt)}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}