import { useExecutionStore } from '../../../stores/executionStore';
import { cn } from '../../../utils/cn';
import type { ExecutionTimelineEvent, TaskStatus } from '../../../types/visualization';

const EVENT_ICONS: Record<string, string> = {
  task_start: '▶️',
  task_complete: '✅',
  task_fail: '❌',
  agent_join: '👋',
  agent_leave: '👋',
  message_sent: '💬',
  round_start: '🔄',
  round_end: '🔚',
};

const EVENT_COLORS: Record<string, string> = {
  task_start: 'bg-blue-100 border-blue-300 text-blue-700',
  task_complete: 'bg-emerald-100 border-emerald-300 text-emerald-700',
  task_fail: 'bg-red-100 border-red-300 text-red-700',
  agent_join: 'bg-purple-100 border-purple-300 text-purple-700',
  agent_leave: 'bg-slate-100 border-slate-300 text-slate-700',
  message_sent: 'bg-sky-100 border-sky-300 text-sky-700',
  round_start: 'bg-amber-100 border-amber-300 text-amber-700',
  round_end: 'bg-orange-100 border-orange-300 text-orange-700',
};

const TASK_STATUS_COLORS: Record<TaskStatus, string> = {
  queued: 'bg-slate-100 text-slate-600 border-slate-300',
  running: 'bg-blue-100 text-blue-600 border-blue-300 animate-pulse',
  completed: 'bg-emerald-100 text-emerald-600 border-emerald-300',
  failed: 'bg-red-100 text-red-600 border-red-300',
  cancelled: 'bg-slate-100 text-slate-400 border-slate-300',
};

export function ExecutionTimeline() {
  const { timelineEvents, tasks, activeSession } = useExecutionStore();

  if (!activeSession) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400">
        <div className="text-center">
          <div className="text-4xl mb-2">⏱️</div>
          <p className="font-medium">暂无执行记录</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white rounded-2xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-slate-200 bg-slate-50">
        <h3 className="font-semibold text-slate-800 flex items-center gap-2">
          <span>⏱️</span> 执行时间线
        </h3>
        {activeSession && (
          <p className="text-xs text-slate-500 mt-1">
            会话: {activeSession.title} | 开始时间: {new Date(activeSession.startTime).toLocaleTimeString()}
          </p>
        )}
      </div>

      {/* Task Status Summary */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-slate-100 bg-slate-50/50">
        <div className="flex gap-2">
          {(['queued', 'running', 'completed', 'failed'] as TaskStatus[]).map((status) => {
            const count = tasks.filter((t) => t.status === status).length;
            return (
              <div
                key={status}
                className={cn(
                  'px-3 py-1.5 rounded-lg border text-xs font-medium',
                  TASK_STATUS_COLORS[status]
                )}
              >
                {getTaskStatusLabel(status)}: {count}
              </div>
            );
          })}
        </div>
      </div>

      {/* Timeline Events */}
      <div className="flex-1 overflow-y-auto p-4">
        {timelineEvents.length === 0 ? (
          <div className="text-center text-slate-400 py-8">
            <div className="text-4xl mb-2">📋</div>
            <p className="text-sm">暂无事件</p>
          </div>
        ) : (
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-5 top-0 bottom-0 w-0.5 bg-slate-200" />

            {/* Events */}
            <div className="space-y-3">
              {timelineEvents.map((event, index) => (
                <TimelineEventItem key={event.id} event={event} isLast={index === timelineEvents.length - 1} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TimelineEventItem({ event, isLast }: { event: ExecutionTimelineEvent; isLast: boolean }) {
  const { timestamp, type, agentId, taskId, details } = event;
  const icon = EVENT_ICONS[type] || '📌';
  const colorClass = EVENT_COLORS[type] || 'bg-slate-100 border-slate-300 text-slate-700';

  const time = new Date(timestamp).toLocaleTimeString();

  return (
    <div className="relative flex gap-3">
      {/* Icon */}
      <div
        className={cn(
          'relative z-10 w-10 h-10 rounded-full border-2 flex items-center justify-center text-lg flex-shrink-0 shadow-sm',
          colorClass
        )}
      >
        {icon}
      </div>

      {/* Content */}
      <div className={cn('flex-1 pb-4', !isLast && 'border-b border-slate-100')}>
        <div className="flex items-center justify-between">
          <span className="font-medium text-sm text-slate-800">{getEventLabel(type)}</span>
          <span className="text-xs text-slate-400">{time}</span>
        </div>

        <div className="mt-1 text-xs text-slate-500">
          {agentId && <span className="mr-2">Agent: {agentId}</span>}
          {taskId && <span>Task: {taskId}</span>}
        </div>

        {details && Object.keys(details).length > 0 && (
          <div className="mt-1 text-xs text-slate-400">
            {'message' in details && <span>{String(details.message)}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function getEventLabel(type: string): string {
  const labels: Record<string, string> = {
    task_start: '任务开始',
    task_complete: '任务完成',
    task_fail: '任务失败',
    agent_join: 'Agent 加入',
    agent_leave: 'Agent 离开',
    message_sent: '发送消息',
    round_start: '轮次开始',
    round_end: '轮次结束',
  };
  return labels[type] || type;
}

function getTaskStatusLabel(status: TaskStatus): string {
  const labels: Record<TaskStatus, string> = {
    queued: '排队中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  };
  return labels[status];
}