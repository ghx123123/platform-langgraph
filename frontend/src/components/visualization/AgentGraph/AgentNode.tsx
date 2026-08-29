import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { cn } from '../../../utils/cn';
import type { AgentNodeData, AgentType } from '../../../types/visualization';

const AGENT_AVATARS: Record<AgentType, string> = {
  proponent: '✅',
  opponent: '❌',
  teacher: '📚',
  student: '🎓',
  supervisor: '👁️',
  moderator: '🎯',
  reporter: '📝',
};

const AGENT_LABELS: Record<AgentType, string> = {
  proponent: '正方',
  opponent: '反方',
  teacher: '教师',
  student: '学生',
  supervisor: '监督',
  moderator: '主持',
  reporter: '汇报',
};

const STATUS_COLORS = {
  idle: 'bg-slate-100 border-slate-300 text-slate-500',
  thinking: 'bg-amber-50 border-amber-300 text-amber-600 ring-2 ring-amber-200',
  speaking: 'bg-blue-50 border-blue-300 text-blue-600 ring-2 ring-blue-200 animate-pulse',
  waiting: 'bg-orange-50 border-orange-300 text-orange-600',
  completed: 'bg-emerald-50 border-emerald-300 text-emerald-600',
  error: 'bg-red-50 border-red-300 text-red-600 ring-2 ring-red-200',
};

function AgentNodeComponent({ data, selected }: NodeProps) {
  const nodeData = data as AgentNodeData;
  const { label, type, status, avatar, currentTask, messageCount } = nodeData;
  const displayAvatar = avatar || AGENT_AVATARS[type as AgentType] || '🤖';
  const displayLabel = label || AGENT_LABELS[type as AgentType] || 'Agent';

  return (
    <div
      className={cn(
        'relative px-4 py-3 rounded-xl border-2 shadow-lg transition-all duration-300 min-w-[140px]',
        STATUS_COLORS[status as keyof typeof STATUS_COLORS],
        selected && 'ring-4 ring-blue-400 ring-offset-2'
      )}
    >
      {/* Connection handles */}
      <Handle type="target" position={Position.Top} className="!bg-slate-400 !w-2 !h-2" />
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400 !w-2 !h-2" />
      <Handle type="target" position={Position.Left} className="!bg-slate-400 !w-2 !h-2" />
      <Handle type="source" position={Position.Right} className="!bg-slate-400 !w-2 !h-2" />

      {/* Agent content */}
      <div className="flex items-center gap-3">
        <div className="text-2xl flex-shrink-0">{displayAvatar}</div>
        <div className="min-w-0">
          <div className="font-semibold text-sm truncate">{displayLabel}</div>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={cn(
                'text-xs px-1.5 py-0.5 rounded-full',
                status === 'thinking' && 'bg-amber-100',
                status === 'speaking' && 'bg-blue-100',
                status === 'waiting' && 'bg-orange-100',
                status === 'completed' && 'bg-emerald-100',
                status === 'error' && 'bg-red-100',
                status === 'idle' && 'bg-slate-100'
              )}
            >
              {getStatusLabel(status)}
            </span>
            {messageCount > 0 && (
              <span className="text-xs text-slate-400">{messageCount} 条消息</span>
            )}
          </div>
          {currentTask && status === 'thinking' && (
            <div className="mt-1 text-xs text-slate-500 truncate max-w-[120px]">
              {currentTask}
            </div>
          )}
        </div>
      </div>

      {/* Speaking indicator */}
      {status === 'speaking' && (
        <div className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 rounded-full animate-ping" />
      )}
    </div>
  );
}

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    idle: '空闲',
    thinking: '思考中',
    speaking: '发言中',
    waiting: '等待',
    completed: '完成',
    error: '错误',
  };
  return labels[status] || status;
}

export const AgentNode = memo(AgentNodeComponent);