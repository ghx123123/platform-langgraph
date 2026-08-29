import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Circle, Loader2 } from 'lucide-react';
import { useState } from 'react';
import './DataProcessingRail.css';

export type DataProcessStatus = 'idle' | 'ready' | 'active' | 'done' | 'warning' | 'error';

export interface DataProcessNode {
  id: string;
  title: string;
  status: DataProcessStatus;
  metric: string;
  message: string;
  duration?: string;
  actionLabel: string;
}

interface Props {
  nodes: DataProcessNode[];
  onAction: (nodeId: string) => void;
}

const statusLabels: Record<DataProcessStatus, string> = {
  idle: '未开始', ready: '可继续', active: '处理中', done: '已完成', warning: '需复核', error: '失败',
};

function StatusIcon({ status }: { status: DataProcessStatus }) {
  if (status === 'active') return <Loader2 className="spin" size={14} />;
  if (status === 'done') return <CheckCircle2 size={14} />;
  if (status === 'warning' || status === 'error') return <AlertTriangle size={14} />;
  return <Circle size={12} />;
}

export function DataProcessingRail({ nodes, onAction }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const expanded = nodes.find((node) => node.id === expandedId) || null;

  return (
    <section className={`data-process-rail ${expanded ? 'is-expanded' : ''}`} aria-label="备课数据处理链">
      <header>
        <div><strong>本次备课数据链</strong><span>点击节点查看状态与下一步</span></div>
        {expanded && <button type="button" onClick={() => setExpandedId(null)} aria-label="收起数据链详情"><ChevronUp size={15} /></button>}
      </header>
      <div className="data-process-nodes">
        {nodes.map((node, index) => (
          <button
            type="button"
            key={node.id}
            className={`process-node status-${node.status} ${expandedId === node.id ? 'selected' : ''}`}
            onClick={() => setExpandedId((current) => current === node.id ? null : node.id)}
            aria-expanded={expandedId === node.id}
          >
            <i><StatusIcon status={node.status} /></i>
            <span><strong>{node.title}</strong><small>{node.metric}</small></span>
            {index < nodes.length - 1 && <em aria-hidden="true">›</em>}
          </button>
        ))}
      </div>
      {expanded && (
        <div className={`data-process-detail status-${expanded.status}`}>
          <span><StatusIcon status={expanded.status} /><strong>{statusLabels[expanded.status]}</strong></span>
          <p>{expanded.message}</p>
          <small>{expanded.metric}{expanded.duration ? ` · 耗时 ${expanded.duration}` : ''}</small>
          <button type="button" onClick={() => onAction(expanded.id)}>{expanded.actionLabel}</button>
          <button type="button" className="detail-collapse" onClick={() => setExpandedId(null)} aria-label="收起详情"><ChevronDown size={14} /></button>
        </div>
      )}
    </section>
  );
}
