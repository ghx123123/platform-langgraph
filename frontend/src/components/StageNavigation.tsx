import { Database, FileOutput, LayoutDashboard, LibraryBig, PanelsTopLeft } from 'lucide-react';

export type AppStage = 'overview' | 'hub' | 'materials' | 'design' | 'exports';

interface Props {
  stage: AppStage;
  onChange: (stage: AppStage) => void;
  archiveCount: number;
  runCount: number;
  designCount: number;
}

const stages = [
  { key: 'overview' as const, label: '中台总览', detail: '全局数据与流转状态', icon: LayoutDashboard },
  { key: 'hub' as const, label: '课程资料库', detail: '本地目录与原始资料', icon: LibraryBig },
  { key: 'materials' as const, label: '资料单元', detail: '原始材料、提取结果与范围确认', icon: Database },
  { key: 'design' as const, label: '课程设计', detail: '材料预览、多智能体生成与打磨', icon: PanelsTopLeft },
  { key: 'exports' as const, label: '成果中心', detail: '教案定稿、资料包与文件导出', icon: FileOutput },
];

export function StageNavigation({ stage, onChange, archiveCount, runCount, designCount }: Props) {
  const counts = { overview: archiveCount + runCount + designCount, hub: archiveCount, materials: archiveCount, design: runCount, exports: designCount };
  return (
    <nav className="stage-navigation" aria-label="备课工作阶段">
      {stages.map((item, index) => {
        const Icon = item.icon;
        return (
          <button type="button" key={item.key} className={stage === item.key ? 'active' : ''} onClick={() => onChange(item.key)} aria-current={stage === item.key ? 'page' : undefined}>
            <span className="stage-index">{index + 1}</span>
            <Icon size={16} />
            <span><strong>{item.label}</strong><small>{item.detail}</small></span>
            <em>{counts[item.key]}</em>
          </button>
        );
      })}
    </nav>
  );
}
