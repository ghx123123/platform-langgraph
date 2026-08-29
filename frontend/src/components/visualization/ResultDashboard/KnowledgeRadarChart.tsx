import { useMemo } from 'react';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { cn } from '../../../utils/cn';
import type { KnowledgeCoverage } from '../../../types/visualization';

interface KnowledgeRadarChartProps {
  knowledgeCoverage: KnowledgeCoverage[];
  className?: string;
}

export function KnowledgeRadarChart({ knowledgeCoverage, className }: KnowledgeRadarChartProps) {
  const chartData = useMemo(() => {
    return knowledgeCoverage.map((kp) => ({
      subject: kp.title.length > 10 ? kp.title.substring(0, 10) + '...' : kp.title,
      fullTitle: kp.title,
      mastery: Math.round(kp.masteryLevel * 100),
      timesAccessed: kp.timesAccessed,
      covered: kp.covered,
    }));
  }, [knowledgeCoverage]);

  const coveredCount = knowledgeCoverage.filter((kp) => kp.covered).length;
  const avgMastery = knowledgeCoverage.length > 0
    ? Math.round(knowledgeCoverage.reduce((sum, kp) => sum + kp.masteryLevel, 0) / knowledgeCoverage.length * 100)
    : 0;

  if (knowledgeCoverage.length === 0) {
    return (
      <div className={cn('flex items-center justify-center h-full text-slate-400', className)}>
        <div className="text-center">
          <div className="text-4xl mb-2">📡</div>
          <p className="text-sm">暂无知识点数据</p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn('bg-white rounded-2xl border border-slate-200 p-6', className)}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-slate-800 flex items-center gap-2">
          <span>📡</span> 知识点掌握雷达图
        </h3>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-500">
            已覆盖: <span className="font-semibold text-emerald-600">{coveredCount}/{knowledgeCoverage.length}</span>
          </span>
          <span className="text-slate-500">
            平均掌握: <span className="font-semibold text-blue-600">{avgMastery}%</span>
          </span>
        </div>
      </div>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={chartData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
            <PolarGrid stroke="#e2e8f0" />
            <PolarAngleAxis
              dataKey="subject"
              tick={{ fontSize: 11, fill: '#64748b' }}
              tickLine={false}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickCount={5}
            />
            <Radar
              name="掌握度"
              dataKey="mastery"
              stroke="#3b82f6"
              fill="#3b82f6"
              fillOpacity={0.3}
              strokeWidth={2}
            />
            <Radar
              name="访问次数"
              dataKey="timesAccessed"
              stroke="#10b981"
              fill="#10b981"
              fillOpacity={0.1}
              strokeWidth={2}
            />
            <Legend
              wrapperStyle={{ fontSize: 12 }}
              iconType="circle"
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend detail */}
      <div className="mt-4 grid grid-cols-2 gap-2">
        {knowledgeCoverage.slice(0, 6).map((kp) => (
          <div
            key={kp.knowledgePointId}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs',
              kp.covered ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-50 text-slate-500'
            )}
          >
            <span>{kp.covered ? '✅' : '⬜'}</span>
            <span className="truncate">{kp.title}</span>
            <span className="ml-auto font-medium">{Math.round(kp.masteryLevel * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}