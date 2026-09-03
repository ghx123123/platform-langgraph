import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2, FileText, Radio,
} from 'lucide-react';
import type { RunEvent, TeachingMessage, WorkflowRun } from '../types/workflow';
import { AGENT_ROLE_DEFINITIONS, type AgentRoleDefinition, type AgentRoleKind, type AgentRolePhase } from '../lib/agentRoles';
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

interface FlowNode {
  key: string;
  name: string;
  role: string;
  responsibility: string;
  input: string;
  output: string;
  phase: AgentRolePhase;
  kind: AgentRoleKind;
  icon: AgentRoleDefinition['icon'];
  state: 'done' | 'running' | 'waiting';
  iteration: number;
  message?: string;
}

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

  const nodes: FlowNode[] = useMemo(() => {
    const hasNodeProgress = events.some((event) => ['node.started', 'node.completed', 'review.completed'].includes(event.event_type));
    return AGENT_ROLE_DEFINITIONS.map((def, index) => {
    const iteration = def.phase === 'teach_knowledge' || def.phase === 'student_question' || def.phase === 'teacher_answer'
      ? Number(run.teaching_data.current_iteration ?? 0)
      : 0;
    const state: FlowNode['state'] = phaseDone(events, def.phase)
      ? 'done'
      : phaseRunning(events, def.phase, run) || (!hasNodeProgress && ['queued', 'running'].includes(run.status) && index === 0) ? 'running' : 'waiting';
    // 该角色最近一条真实产出
    const latestMsg = [...messages].reverse().find((m) => m.phase === def.phase);
      return { key: def.key, name: def.name, role: def.role, responsibility: def.responsibility, input: def.input, output: def.output, phase: def.phase, kind: def.kind, icon: def.icon, state, iteration, message: latestMsg?.content || '' };
    });
  }, [events, messages, run]);

  const selectedNode = nodes.find((n) => n.key === selected) || nodes[0];
  const chatMessages = useMemo(() => messages.slice(-8), [messages]);

  // Focus the live agent automatically when a run starts or advances.
  useEffect(() => {
    const running = nodes.find((node) => node.state === 'running');
    if (running) setSelected(running.key);
  }, [run.id, events.length]);

  // 节点 key → workflow phase 映射(node.token 事件的 node 字段用的是 phase)
  const rolePhase = selectedNode?.phase;
  // 真实 token 流: 从 events 提取 node.token(按 node 分组的累积文本), 供右侧 dsh 流展示"真实正在生成"
  const tokenTexts = useMemo(() => {
    const map: Record<string, string> = {};
    events.forEach((event) => {
      if (event.event_type === 'node.token' && event.node) {
        const text = (event.payload && event.payload.text) ? String(event.payload.text) : '';
        map[event.node] = (map[event.node] || '') + text;
      }
    });
    return map;
  }, [events]);
  const liveTokenText = rolePhase ? tokenTexts[rolePhase] || '' : '';
  const hasLiveToken = liveTokenText.length > 0;
  // A persisted terminal status is authoritative. Historical token events are
  // replayed as read-only content and must not make the panel look live.
  const isTerminalRun = ['completed', 'failed', 'cancelled'].includes(run.status);
  const shouldStream = !isTerminalRun && selectedNode?.state === 'running';

  // dsh 生成过程: running 时用真实 node.token 流; 否则回退打字流(展示已有 message)
  useEffect(() => {
    setStreamDone(false);
    setStreaming(shouldStream);
    if (streamTimer.current) clearInterval(streamTimer.current);
    const body = streamBodyRef.current;
    // 真 token 流: 直接累积渲染(新事件到达自动追加)
    if (hasLiveToken) {
      if (body) { body.textContent = liveTokenText; body.scrollTop = body.scrollHeight; }
      setStreamDone(!shouldStream);
      setStreaming(shouldStream);
      return () => { if (streamTimer.current) clearInterval(streamTimer.current); };
    }
    const text = (selectedNode?.message || `正在通过 dsh agent 处理「${selectedNode?.name || '当前'}」任务…`)
      .replace(/<\\?[a-z/][^>]*>/gi, '');
    if (!shouldStream) {
      if (body) { body.textContent = text; body.scrollTop = body.scrollHeight; }
      setStreaming(false);
      setStreamDone(Boolean(selectedNode?.message) || selectedNode?.state === 'done' || isTerminalRun);
      return () => { if (streamTimer.current) clearInterval(streamTimer.current); };
    }
    if (body) {
      body.textContent = '';
      let i = 0;
      streamTimer.current = setInterval(() => {
        if (i >= text.length) {
          clearInterval(streamTimer.current);
          streamTimer.current = undefined;
          setStreaming(false);
          setStreamDone(true);
          if (body) body.textContent = text;
          return;
        }
        i += 2;
        if (body) {
          body.textContent = text.slice(0, i);
          body.scrollTop = body.scrollHeight;
        }
      }, 18);
    }
    return () => { if (streamTimer.current) clearInterval(streamTimer.current); };
  }, [selected, selectedNode?.message, selectedNode?.state, liveTokenText, hasLiveToken, shouldStream, isTerminalRun]);

  const runningCount = nodes.filter((n) => n.state === 'running').length;
  const doneCount = nodes.filter((n) => n.state === 'done').length;

  // 画布布局锚点(与原型一致): 主线 y=204 水平 4 个 + 学生列 x=690 + 第二行 y=400
  const LAYOUT: Record<string, { x: number; y: number }> = {
    analysis: { x: 10, y: 48 }, design: { x: 200, y: 48 }, teach: { x: 390, y: 48 },
    students: { x: 10, y: 205 }, answer: { x: 150, y: 205 },
    supervisor: { x: 290, y: 205 }, finalize: { x: 430, y: 205 },
  };
  const EDGES: Array<{ from: string; cls: string; d: string }> = [
    { from: 'analysis', cls: '', d: 'M140 74 L200 74' },
    { from: 'design', cls: '', d: 'M330 74 L390 74' },
    { from: 'teach', cls: 'extra', d: 'M455 111 C455 150 75 150 75 205' },
    { from: 'students', cls: '', d: 'M140 231 L150 231' },
    { from: 'answer', cls: 'super', d: 'M280 231 L290 231' },
    { from: 'supervisor', cls: '', d: 'M420 231 L430 231' },
  ];

  return (
    <div className="afw-root">
      {/* 顶部: 流程标题 + 团队进度 + 状态 */}
      <div className="afw-top">
        <div className="afw-top-title"><h3>角色协作工作台</h3><span>每个角色独立负责一类产出，通过明确输入/输出进行协作</span></div>
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
          <div className="afw-roster-head">角色目录 <span>{nodes.length}</span></div>
          <div className="afw-roster-list">
            {nodes.map((node) => {
              const Icon = node.icon;
              return (
                <button key={node.key} type="button" className={`afw-member ${selected === node.key ? 'active' : ''}`} onClick={() => setSelected(node.key)}>
                  <span className={`afw-member-ico kind-${node.kind}`}><Icon size={14} /></span>                  <span className="afw-member-info"><b>{node.name}</b><small>{node.role}</small></span>
                  <span className={`afw-member-state state-${node.state}`}>
                    {node.state === 'running' && <i className="afw-pulse" />}
                    {node.state === 'done' ? <CheckCircle2 size={12} /> : null}
                    {node.state === 'running' ? '工作中' : node.state === 'done' ? '已交付' : '待命'}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="afw-roster-foot">点击角色查看其专属 dsh 产出</div>
        </aside>

        {/* 中: 流程图 */}
        <div className="afw-canvas-wrap">
          <div className="afw-canvas scale-fit" style={{ '--afw-scale': '0.72' } as React.CSSProperties}>
          <svg className="afw-edges" width="560" height="330" viewBox="0 0 560 330" aria-hidden>
            <defs><marker id="afw-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7 Z" fill="currentColor" /></marker></defs>
            {EDGES.map((edge, index) => {
              const from = nodes.find((n) => n.key === edge.from);
              const done = from?.state === 'done';
              return <path key={`${edge.from}-${index}`} className={`afw-edge ${edge.cls} ${done ? 'done' : ''}`} d={edge.d} markerEnd="url(#afw-arrow)" />;
            })}
          </svg>
          <div className="afw-nodes">
            {nodes.map((node) => {
              const Icon = node.icon;
              const pos = LAYOUT[node.key];
              if (!pos) return null;
              return (
                <button key={node.key} type="button" className={`afw-node state-${node.state} ${selected === node.key ? 'active' : ''}`}
                  style={{ left: `${pos.x}px`, top: `${pos.y}px`, width: '130px' }}
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
        </div>

        {/* Linear fallback keeps the same event-backed states usable on touch
            screens where the spatial SVG cannot fit without horizontal scroll. */}
        <div className="afw-mobile-flow" aria-label="智能体执行顺序">
          {nodes.map((node, index) => {
            const Icon = node.icon;
            return (
              <button
                key={node.key}
                type="button"
                className={`afw-mobile-step state-${node.state} ${selected === node.key ? 'active' : ''}`}
                onClick={() => setSelected(node.key)}
              >
                <span className="afw-mobile-index">{node.state === 'done' ? <CheckCircle2 size={14} /> : index + 1}</span>
                <span className={`afw-member-ico kind-${node.kind}`}><Icon size={14} /></span>
                <span className="afw-mobile-copy"><b>{node.name}</b><small>{node.role}</small></span>
                <span className="afw-mobile-status">{node.state === 'done' ? '已完成' : node.state === 'running' ? '进行中' : '待启动'}</span>
              </button>
            );
          })}
        </div>

        {/* 右: 节点详情 */}
        <aside className="afw-detail">
          <div className="afw-detail-head">
            <span className={`afw-detail-ico kind-${selectedNode.kind}`}><FileText size={16} /></span>
            <span className="afw-detail-t"><b>{selectedNode.name}</b><small>{selectedNode.role}</small></span>
            <span className={`afw-detail-badge state-${selectedNode.state}`}>{selectedNode.state === 'done' ? '已完成' : selectedNode.state === 'running' ? '进行中' : '待启动'}</span>
          </div>
          <div className="afw-detail-meta">
            <span><b>职责边界：</b>{selectedNode.responsibility}</span>
            <span><b>输入：</b>{selectedNode.input}</span>
            <span><b>输出：</b>{selectedNode.output}</span>
            <span><b>当前轮次：</b>{selectedNode.iteration > 0 ? `第 ${selectedNode.iteration} 轮` : '教学准备'}</span>
          </div>

          <div className="afw-detail-sec">
            <div className="afw-sec-title"><Radio size={13} />dsh 生成过程 <em className="afw-live">{streaming ? '● 实时流' : streamDone ? (isTerminalRun ? '● 历史回放' : '● 完成') : '● 待开始'}</em></div>
            <div className={`afw-dsh ${streaming ? 'is-streaming' : ''}`}>
              <div className="afw-dsh-head"><b>dsh-agent · {selectedNode.name} · deepseek-v4-flash</b><span>{streaming ? '生成中' : streamDone ? '已完成' : '空闲'}</span></div>
              <div className="afw-dsh-body" ref={streamBodyRef} />
              <div className="afw-dsh-foot">{streaming ? `调用 generate · 第 ${selectedNode.iteration > 0 ? selectedNode.iteration : 1}/3 轮` : streamDone ? (isTerminalRun ? '本次会话已结束，可回放生成记录' : '交付完成，等待下游任务认领') : '等待进入本轮任务队列'}</div>
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
