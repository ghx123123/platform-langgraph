import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2, Clipboard, FileText, GraduationCap, Layers3, Radio,
  ShieldCheck, Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { RunEvent, TeachingMessage, WorkflowRun } from '../types/workflow';
import './AgentFlowWorkspace.css';

/**
 * 多智能体协作流程视图 (Agent Flow Workspace)
 *
 * 参考 docs/course-design-agent-team-preview.html 原型, 接入真实事件流:
 * - 中央流程图: 节点状态由 events(node.started/completed/run.heartbeat) 推导
 * - 右侧节点详情: 展示该角色最近一条产出(真实 message) 的 dsh 生成过程(打字流模拟 token)
 * - 左/下方: 团队名册 + 实时通信(真实 messages 气泡)
 * 数据源全部为现有 events/messages, 无额外后端依赖; 版式为增强(可通过 tab 与旧三列视图切换)。
 */

interface AgentFlowWorkspaceProps {
  run: WorkflowRun;
  events: RunEvent[];
  messages: TeachingMessage[];
}

type NodePhase = 'content_analysis' | 'teaching_design' | 'teach_knowledge' | 'student_question' | 'teacher_answer' | 'supervisor_comment' | 'finalize';

interface FlowNode {
  key: string;
  name: string;
  role: string;
  kind: 'analyst' | 'designer' | 'teacher' | 'student' | 'supervisor' | 'finalizer';
  state: 'done' | 'running' | 'waiting';
  iteration: number;
  message?: string;
}

const NODE_ORDER: Array<{ key: string; name: string; role: string; kind: FlowNode['kind']; phase: NodePhase }> = [
  { key: 'analysis', name: '教材分析员', role: '内容剖析 · 重难点', kind: 'analyst', phase: 'content_analysis' },
  { key: 'design', name: '教学设计员', role: '目标 · 环节 · 练习', kind: 'designer', phase: 'teaching_design' },
  { key: 'teach', name: '讲授教师', role: '生成回答 · 整合建议', kind: 'teacher', phase: 'teach_knowledge' },
  { key: 'students', name: '分层学生', role: '拓展/进阶/基础问题', kind: 'student', phase: 'student_question' },
  { key: 'answer', name: '教师答疑', role: '回应学生 · 澄清误区', kind: 'teacher', phase: 'teacher_answer' },
  { key: 'supervisor', name: '教学督导', role: '评分 · 改进建议', kind: 'supervisor', phase: 'supervisor_comment' },
  { key: 'finalize', name: '成果整理员', role: '汇总交付', kind: 'finalizer', phase: 'finalize' },
];

const KIND_ICON: Record<FlowNode['kind'], LucideIcon> = {
  analyst: FileText, designer: Layers3, teacher: GraduationCap,
  student: Users, supervisor: ShieldCheck, finalizer: Clipboard,
};

function phaseDone(events: RunEvent[], phase: string): boolean {
  return events.some((e) => ['node.completed', 'review.completed'].includes(e.event_type) && e.node === phase);
}

function phaseRunning(events: RunEvent[], phase: string, run: WorkflowRun): boolean {
  if (run.status === 'completed' || run.status === 'failed') return false;
  const latest = [...events].reverse().find((e) => e.node === phase && e.event_type === 'node.started');
  return latest !== undefined;
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '--:--' : date.toLocaleTimeString('zh-CN', { hour12: false });
}

export function AgentFlowWorkspace({ run, events, messages }: AgentFlowWorkspaceProps) {
  const [selected, setSelected] = useState<string>('teach');
  const [streaming, setStreaming] = useState(false);
  const [streamDone, setStreamDone] = useState(false);
  const streamBodyRef = useRef<HTMLDivElement | null>(null);
  const streamTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const nodes: FlowNode[] = useMemo(() => NODE_ORDER.map((def) => {
    const iteration = def.phase === 'teach_knowledge' || def.phase === 'student_question' || def.phase === 'teacher_answer'
      ? Number(run.teaching_data.current_iteration ?? 0)
      : 0;
    const state: FlowNode['state'] = phaseDone(events, def.phase)
      ? 'done'
      : phaseRunning(events, def.phase, run) ? 'running' : 'waiting';
    // 该角色最近一条真实产出
    const latestMsg = [...messages].reverse().find((m) => m.phase === def.phase);
    return { key: def.key, name: def.name, role: def.role, kind: def.kind, state, iteration, message: latestMsg?.content || '' };
  }), [events, messages, run]);

  const selectedNode = nodes.find((n) => n.key === selected) || nodes[0];
  const chatMessages = useMemo(() => messages.slice(-8), [messages]);

  // dsh 生成过程: 基于选中节点的真实 message, 打字流逐字显示
  useEffect(() => {
    setStreamDone(false);
    setStreaming(true);
    if (streamTimer.current) clearInterval(streamTimer.current);
    const text = selectedNode?.message || `正在通过 dsh agent 处理「${selectedNode?.name || '当前'}」任务…`;
    const body = streamBodyRef.current;
    if (body) {
      body.innerHTML = '<span class="afw-stream-cursor"></span>';
      let i = 0;
      streamTimer.current = setInterval(() => {
        if (i >= text.length) {
          clearInterval(streamTimer.current);
          streamTimer.current = undefined;
          setStreaming(false);
          setStreamDone(true);
          if (body) body.innerHTML = text.replace(/\n/g, '<br>');
          return;
        }
        i += 2;
        if (body) {
          body.innerHTML = text.slice(0, i).replace(/\n/g, '<br>') + '<span class="afw-stream-cursor"></span>';
          body.scrollTop = body.scrollHeight;
        }
      }, 18);
    }
    return () => { if (streamTimer.current) clearInterval(streamTimer.current); };
  }, [selected, selectedNode?.message]);

  const runningCount = nodes.filter((n) => n.state === 'running').length;
  const doneCount = nodes.filter((n) => n.state === 'done').length;

  return (
    <div className="afw-root">
      {/* 顶部: 流程标题 + 团队进度 + 状态 */}
      <div className="afw-top">
        <div className="afw-top-title"><h3>多智能体协作流程</h3><span>团队A 备课设计组 · 团队B 课堂互动组 · 团队C 督导优化组</span></div>
        <div className="afw-top-progress">
          <span className={`afw-progress-pill ${runningCount > 0 ? 'run' : doneCount === nodes.length ? 'done' : 'wait'}`}>
            <Radio size={12} />{runningCount > 0 ? `${runningCount} 个智能体执行中` : doneCount === nodes.length ? '全部任务已交付' : '等待调度'}
          </span>
          <span className="afw-progress-pct">{doneCount}/{nodes.length} 完成</span>
        </div>
      </div>

      {/* 主体: 名册 | 流程图 | 详情 */}
      <div className="afw-body">
        {/* 左: 团队名册 */}
        <aside className="afw-roster">
          <div className="afw-roster-head">团队成员 <span>{nodes.length}</span></div>
          <div className="afw-roster-list">
            {nodes.map((node) => {
              const Icon = KIND_ICON[node.kind];
              return (
                <button key={node.key} type="button" className={`afw-member ${selected === node.key ? 'active' : ''}`} onClick={() => setSelected(node.key)}>
                  <span className={`afw-member-ico kind-${node.kind}`}><Icon size={14} /></span>
                  <span className="afw-member-info"><b>{node.name}</b><small>{node.role}</small></span>
                  <span className={`afw-member-state state-${node.state}`}>
                    {node.state === 'running' && <i className="afw-pulse" />}
                    {node.state === 'done' ? <CheckCircle2 size={12} /> : null}
                    {node.state === 'running' ? '工作中' : node.state === 'done' ? '已交付' : '待命'}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="afw-roster-foot">点击成员查看 dsh 生成过程</div>
        </aside>

        {/* 中: 流程图 */}
        <div className="afw-canvas-wrap">
          <svg className="afw-edges" width="100%" height="100%" viewBox="0 0 900 560" preserveAspectRatio="xMidYMid meet" aria-hidden>
            {nodes.slice(0, 6).map((node, index) => {
              const next = nodes[index + 1];
              if (!next) return null;
              const x1 = 70 + index * 150, y1 = 260;
              const x2 = 70 + (index + 1) * 150, y2 = 260;
              const done = node.state === 'done';
              return <path key={node.key} className={`afw-edge ${done ? 'done' : ''}`} d={`M${x1 + 52} ${y1}C${x1 + 90} ${y1},${x2 - 90} ${y2},${x2 - 52} ${y2}`} />;
            })}
            {/* 学生 → 教师答疑 连线 */}
            <path className="afw-edge afw-edge-extra" d="M370 330 C470 420 560 420 640 330" />
            {/* 督导 → 设计 回环 */}
            <path className="afw-edge afw-edge-super" d="M700 260 C700 180 520 130 370 130" />
          </svg>
          <div className="afw-nodes">
            {nodes.map((node, index) => {
              const Icon = KIND_ICON[node.kind];
              const left = 70 + index * 150;
              return (
                <button key={node.key} type="button" className={`afw-node state-${node.state} ${selected === node.key ? 'active' : ''}`}
                  style={{ left: `${left}px`, top: node.key === 'students' ? '300px' : node.key === 'answer' ? '300px' : '230px' }}
                  onClick={() => setSelected(node.key)}>
                  {node.state === 'running' && <span className="afw-node-frame" />}
                  <span className={`afw-node-ico kind-${node.kind}`}><Icon size={16} /><i className="afw-node-dot" /></span>
                  <span className="afw-node-txt"><b>{node.name}</b><small>{node.role}</small><em>{node.state === 'done' ? '已完成' : node.state === 'running' ? '进行中' : '待启动'}</em></span>
                </button>
              );
            })}
          </div>
          <div className="afw-legend">
            <span><i className="lg-done" />已完成</span>
            <span><i className="lg-run" />进行中</span>
            <span><i className="lg-wait" />待启动</span>
            <span className="lg-line"><i className="lg-line1" />消息流</span>
            <span className="lg-line"><i className="lg-line2" />督导流</span>
          </div>
        </div>

        {/* 右: 节点详情 */}
        <aside className="afw-detail">
          <div className="afw-detail-head">
            <span className={`afw-detail-ico kind-${selectedNode.kind}`}><FileText size={16} /></span>
            <span className="afw-detail-t"><b>{selectedNode.name}</b><small>{selectedNode.role}</small></span>
            <span className={`afw-detail-badge state-${selectedNode.state}`}>{selectedNode.state === 'done' ? '已完成' : selectedNode.state === 'running' ? '进行中' : '待启动'}</span>
          </div>
          <div className="afw-detail-meta">
            <span>所属团队：{selectedNode.kind === 'supervisor' ? '团队C' : selectedNode.kind === 'student' ? '团队B' : '团队A'}</span>
            <span>轮次：{selectedNode.iteration > 0 ? `第 ${selectedNode.iteration} 轮` : '教学准备'}</span>
            <span>成员名册：{nodes.map((n) => n.name.split('·')[0].slice(0, 2)).join(' / ')}</span>
          </div>

          <div className="afw-detail-sec">
            <div className="afw-sec-title"><Radio size={13} />dsh 生成过程 <em className="afw-live">{streaming ? '● 实时流' : streamDone ? '● 完成' : '● 待开始'}</em></div>
            <div className="afw-dsh">
              <div className="afw-dsh-head"><b>dsh-agent · {selectedNode.name} · deepseek-v4-flash</b><span>{streaming ? '生成中' : streamDone ? '已完成' : '空闲'}</span></div>
              <div className="afw-dsh-body" ref={streamBodyRef} />
              <div className="afw-dsh-foot">{streaming ? `调用 generate · 第 ${selectedNode.iteration > 0 ? selectedNode.iteration : 1}/3 轮` : streamDone ? '交付完成，等待下游任务认领' : '等待进入本轮任务队列'}</div>
            </div>
          </div>

          <div className="afw-detail-sec">
            <div className="afw-sec-title">实时通信 <span>{chatMessages.length} 条</span></div>
            <div className="afw-chat">
              {chatMessages.length === 0 ? <p className="afw-chat-empty">暂无消息，等智能体开始产出…</p> : chatMessages.map((msg, index) => (
                <div key={`${msg.id}-${index}`} className={`afw-msg ${msg.agent_type === 'student' ? 'from-student' : ''}`}>
                  <span className="afw-msg-ava">{msg.agent_name?.slice(0, 1) || 'A'}</span>
                  <span className="afw-msg-body"><b>{msg.agent_name}</b><i>{formatTime(msg.created_at || '')}</i><p>{msg.content}</p></span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
