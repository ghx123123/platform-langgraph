import { useEffect, useMemo, useState } from 'react';
import { Activity, CheckCircle2, ChevronDown, Clock3, Cpu, Radio, Timer, Zap } from 'lucide-react';
import type { RunEvent, WorkflowRun } from '../types/workflow';
import './GenerationStatusPanel.css';

interface ModelMetrics {
  request_count: number;
  response_ms: number;
  max_response_ms: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated: boolean;
  output_tokens_per_second: number;
}

const nodeDetails: Record<string, { owner: string; task: string }> = {
  content_analysis: { owner: '课程教师', task: '扫描全文分区，提取知识结构、重难点与误区' },
  teaching_design: { owner: '教学设计教师', task: '组织学习目标、教学环节、练习与评价方式' },
  teach_knowledge: { owner: '课程教师', task: '围绕指定范围生成本轮讲授方案' },
  student_question: { owner: '三类学生智能体', task: '并行生成拓展、进阶与基础层次问题' },
  teacher_answer: { owner: '课程教师', task: '逐层回应学生问题并澄清概念边界' },
  supervisor_comment: { owner: '教学督导', task: '评价课堂质量并凝练下一轮优化提示词' },
  finalize: { owner: '资料整理器', task: '汇总教学设计、课堂记录与督导结论' },
};

function formatDuration(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

export function GenerationStatusPanel({ run, events, connection }: { run: WorkflowRun; events: RunEvent[]; connection: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (run.status !== 'running' && run.status !== 'queued') return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [run.status]);

  const latestStarted = useMemo(() => [...events].reverse().find((event) => event.event_type === 'node.started'), [events]);
  const latestHeartbeat = useMemo(() => [...events].reverse().find((event) => event.event_type === 'run.heartbeat'), [events]);
  const latestCompleted = useMemo(() => [...events].reverse().find((event) => ['node.completed', 'review.completed'].includes(event.event_type)), [events]);
  const currentNode = (run.status === 'running' || run.status === 'queued')
    ? latestStarted?.node || run.current_node || 'content_analysis'
    : run.current_node || latestStarted?.node || 'content_analysis';
  const detail = nodeDetails[currentNode] || { owner: '教学智能体', task: latestStarted?.message || '正在处理当前任务' };
  const startedAt = String(latestStarted?.payload.task_started_at || latestStarted?.created_at || run.updated_at);
  const elapsed = Math.max(0, now - new Date(startedAt).getTime());
  const completedSteps = Number(latestHeartbeat?.payload.completed_steps ?? latestCompleted?.payload.completed_steps ?? events.filter((event) => ['node.completed', 'review.completed'].includes(event.event_type)).length);
  const expectedSteps = 2 + 5 * Math.max(1, Number(run.teaching_data.max_iterations || 1));
  const totalSteps = Number(latestHeartbeat?.payload.total_steps ?? latestStarted?.payload.total_steps ?? latestCompleted?.payload.total_steps ?? expectedSteps);
  const stepIndex = Number(latestHeartbeat?.payload.step_index ?? latestStarted?.payload.step_index ?? Math.min(totalSteps, completedSteps + 1));
  const progress = Math.min(1, completedSteps / Math.max(totalSteps, 1));
  const metrics = latestCompleted?.payload.model_metrics as unknown as ModelMetrics | undefined;
  const lastSignal = latestHeartbeat || events[events.length - 1];
  const signalAge = lastSignal ? Math.max(0, now - new Date(lastSignal.created_at).getTime()) : 0;
  const heartbeatAge = latestHeartbeat ? Math.max(0, now - new Date(latestHeartbeat.created_at).getTime()) : Number.POSITIVE_INFINITY;
  const healthy = connection === 'live' && heartbeatAge < 22000;
  const healthLabel = healthy
    ? '后端心跳正常'
    : connection === 'connecting' || connection === 'idle'
      ? '正在连接实时进度'
      : connection === 'live'
        ? '等待首次心跳'
        : '实时连接暂不可用';
  const recent = events.filter((event) => ['node.started', 'node.completed', 'review.completed', 'node.degraded'].includes(event.event_type)).slice(-8).reverse();

  return (
    <section className="generation-status" aria-live="polite">
      <div className="generation-main">
        <div className="generation-pulse"><Activity size={18} /><i /></div>
        <div className="generation-task"><span>{detail.owner} · 第 {stepIndex}/{totalSteps} 步</span><strong>{latestStarted?.message || '正在启动课程材料分析'}</strong><small>{detail.task}</small></div>
        <div className="generation-health"><span className={healthy ? 'healthy' : 'waiting'}><Radio size={12} />{healthLabel}</span><small>{formatDuration(elapsed)} · {signalAge < 2000 ? '刚刚更新' : `${formatDuration(signalAge)}前更新`}</small></div>
      </div>
      <div className="generation-progress"><i style={{ transform: `scaleX(${progress})` }} /><span>{Math.round(progress * 100)}%</span></div>
      <details className="generation-details">
        <summary><ChevronDown size={13} />运行详情</summary>
        <div className="generation-details-content"><div className="generation-metrics">
          <span><Timer size={13} /><small>当前任务</small><strong>{formatDuration(elapsed)}</strong></span>
          <span><Clock3 size={13} /><small>上次模型响应</small><strong>{metrics ? formatDuration(metrics.response_ms) : '等待中'}</strong></span>
          <span><Cpu size={13} /><small>Token</small><strong>{metrics ? `${metrics.estimated ? '约 ' : ''}${metrics.total_tokens.toLocaleString()}` : '--'}</strong></span>
          <span><Zap size={13} /><small>输出速度</small><strong>{metrics?.output_tokens_per_second ? `${metrics.output_tokens_per_second} tok/s` : '--'}</strong></span>
        </div><div className="generation-events">{recent.map((event) => <div key={event.sequence} className={`event-${event.event_type.replace('.', '-')}`}><span>{['node.completed', 'review.completed'].includes(event.event_type) ? <CheckCircle2 size={13} /> : <i />}</span><p>{event.message}<small>{new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false })}{event.payload.duration_ms ? ` · ${formatDuration(Number(event.payload.duration_ms))}` : ''}</small></p></div>)}</div></div>
      </details>
    </section>
  );
}
