import { cn } from '../../../utils/cn';
import type { ExecutionStatistics } from '../../../types/visualization';

interface StatisticsPanelProps {
  statistics: ExecutionStatistics | null;
  className?: string;
}

export function StatisticsPanel({ statistics, className }: StatisticsPanelProps) {
  if (!statistics) {
    return (
      <div className={cn('flex items-center justify-center h-full text-slate-400', className)}>
        <div className="text-center">
          <div className="text-4xl mb-2">📊</div>
          <p className="text-sm">暂无统计数据</p>
        </div>
      </div>
    );
  }

  const { totalDuration, totalTokens, totalMessages, averageResponseTime, taskCompletionRate } = statistics;

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}秒`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}分${secs}秒`;
  };

  const formatResponseTime = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div className={cn('bg-white rounded-2xl border border-slate-200 p-6', className)}>
      <h3 className="font-semibold text-slate-800 flex items-center gap-2 mb-4">
        <span>📊</span> 执行统计
      </h3>

      <div className="grid grid-cols-2 gap-4">
        {/* Duration */}
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-100">
          <div className="text-2xl font-bold text-blue-600">{formatDuration(totalDuration)}</div>
          <div className="text-xs text-blue-500 mt-1">总耗时</div>
        </div>

        {/* Tokens */}
        <div className="bg-gradient-to-br from-purple-50 to-pink-50 rounded-xl p-4 border border-purple-100">
          <div className="text-2xl font-bold text-purple-600">
            {totalTokens.toLocaleString()}
          </div>
          <div className="text-xs text-purple-500 mt-1">Token 消耗</div>
        </div>

        {/* Messages */}
        <div className="bg-gradient-to-br from-emerald-50 to-teal-50 rounded-xl p-4 border border-emerald-100">
          <div className="text-2xl font-bold text-emerald-600">{totalMessages}</div>
          <div className="text-xs text-emerald-500 mt-1">消息数量</div>
        </div>

        {/* Response Time */}
        <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-xl p-4 border border-amber-100">
          <div className="text-2xl font-bold text-amber-600">
            {formatResponseTime(averageResponseTime)}
          </div>
          <div className="text-xs text-amber-500 mt-1">平均响应</div>
        </div>
      </div>

      {/* Task Completion Rate */}
      <div className="mt-4 bg-slate-50 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-slate-600">任务完成率</span>
          <span className="text-lg font-bold text-slate-700">
            {Math.round(taskCompletionRate * 100)}%
          </span>
        </div>
        <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-emerald-400 to-teal-500 rounded-full transition-all duration-500"
            style={{ width: `${taskCompletionRate * 100}%` }}
          />
        </div>
      </div>

      {/* Agent Activity */}
      {Object.keys(statistics.agentActivity).length > 0 && (
        <div className="mt-4">
          <h4 className="text-sm font-medium text-slate-600 mb-2">Agent 活跃度</h4>
          <div className="space-y-2">
            {Object.entries(statistics.agentActivity).map(([agentId, count]) => {
              const maxCount = Math.max(...Object.values(statistics.agentActivity));
              const percentage = (count / maxCount) * 100;

              return (
                <div key={agentId} className="flex items-center gap-2">
                  <div className="w-20 text-xs text-slate-500 truncate">{agentId}</div>
                  <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-blue-400 to-indigo-500 rounded-full"
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                  <div className="w-8 text-xs text-slate-500 text-right">{count}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}