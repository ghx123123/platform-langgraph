import { useState, useEffect, useRef } from 'react';
import { DebateSession, DebateAgent, DebateMessage, DebateReport } from '../../types';
import { AgentGraphView } from '../visualization/AgentGraph';
import { ExecutionTimeline } from '../visualization/TaskBoard';
import { StatisticsPanel } from '../visualization/ResultDashboard';
import { useExecutionStore } from '../../stores/executionStore';
import { cn } from '../../utils/cn';

interface EnhancedDebateWindowProps {
  sessionId: string;
  onClose?: () => void;
}

interface RoundGroup {
  round: number;
  messages: DebateMessage[];
}

type ViewMode = 'graph' | 'timeline' | 'stats';

export function EnhancedDebateWindow({ sessionId, onClose }: EnhancedDebateWindowProps) {
  const [session, setSession] = useState<DebateSession | null>(null);
  const [agents, setAgents] = useState<DebateAgent[]>([]);
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [report, setReport] = useState<DebateReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [currentRound, setCurrentRound] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>('graph');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastMsgCountRef = useRef(0);

  // Execution store for visualization
  const {
    setAgentNodes,
    addAgentEdge,
    updateAgentStatus,
    addMessage,
    setActiveSession,
  } = useExecutionStore();

  // Initialize execution store with debate agents
  useEffect(() => {
    if (agents.length > 0) {
      const nodes = agents.map((agent) => ({
        id: agent.id,
        label: getAgentName(agent.role),
        type: agent.role,
        status: (agent.status === 'debating' ? 'speaking' : agent.status === 'ready' ? 'idle' : 'waiting') as import('../../types/visualization').AgentStatus,
        avatar: getAgentAvatar(agent.role),
        messageCount: messages.filter((m) => m.agent_id === agent.id).length,
      }));
      setAgentNodes(nodes);
    }
  }, [agents, messages, setAgentNodes]);

  // Update active agent when message arrives
  useEffect(() => {
    if (messages.length > lastMsgCountRef.current) {
      const latestMsg = messages[messages.length - 1];
      setActiveAgent(latestMsg.agent_id);

      // Add edge for message flow visualization
      const fromAgent = agents.find((a) => a.id === latestMsg.agent_id);
      if (fromAgent) {
        // Determine target based on message context
        const targetRole = latestMsg.agent_role === 'proponent' ? 'opponent' : 'proponent';
        const targetAgent = agents.find((a) => a.role === targetRole);

        if (targetAgent) {
          addAgentEdge({
            id: `${latestMsg.agent_id}-${targetAgent.id}-${messages.length}`,
            source: latestMsg.agent_id,
            target: targetAgent.id,
            type: 'message',
            count: 1,
            lastMessage: latestMsg.content.substring(0, 50),
            animated: true,
          });
        }

        // Update message count
        updateAgentStatus(latestMsg.agent_id, 'idle');
      }

      // Add message to stream
      addMessage({
        id: latestMsg.id,
        fromAgent: latestMsg.agent_id,
        fromAgentLabel: getAgentName(latestMsg.agent_role),
        toAgent: 'broadcast',
        toAgentLabel: '所有人',
        content: latestMsg.content,
        timestamp: latestMsg.created_at,
        type: 'debate',
        animated: true,
      });

      lastMsgCountRef.current = messages.length;

      // Clear active agent after a delay
      setTimeout(() => setActiveAgent(null), 2000);
    }
  }, [messages, agents, addAgentEdge, updateAgentStatus, addMessage]);

  // Fetch session details
  useEffect(() => {
    fetchSession();
  }, [sessionId]);

  // Poll for updates
  useEffect(() => {
    if (!sessionId) return;

    const pollInterval = setInterval(async () => {
      try {
        const sessionRes = await fetch(`/api/debate/sessions/${sessionId}`);
        if (sessionRes.ok) {
          const sessionData = await sessionRes.json();
          setSession(sessionData.session);
          setCurrentRound(sessionData.session.current_round || 0);

          if (sessionData.session.status === 'active') {
            updateAgentStatus(sessionData.agents?.find((a: DebateAgent) =>
              a.status === 'debating'
            )?.id || '', 'speaking');
          }

          if (sessionData.session.status === 'completed' && !report) {
            const reportRes = await fetch(`/api/debate/sessions/${sessionId}/report`);
            if (reportRes.ok) {
              const reportData = await reportRes.json();
              setReport(reportData);
            }
          }
        }

        const msgRes = await fetch(`/api/debate/sessions/${sessionId}/messages`);
        if (msgRes.ok) {
          const msgData = await msgRes.json();
          if (msgData.messages?.length !== lastMsgCountRef.current) {
            setMessages(msgData.messages);
            lastMsgCountRef.current = msgData.messages.length;
            scrollToBottom();
          }
        }
      } catch (e) {
        console.error('[Debate] Poll error:', e);
      }
    }, 2000);

    setLoading(false);

    return () => clearInterval(pollInterval);
  }, [sessionId, session?.status, report, updateAgentStatus]);

  // Set active session when entering
  useEffect(() => {
    if (session) {
      setActiveSession({
        id: session.id,
        type: 'debate',
        status: session.status === 'completed' ? 'completed' : session.status === 'active' ? 'active' : 'pending',
        title: session.title,
        startTime: session.created_at,
        currentRound: session.current_round,
        maxRounds: session.max_rounds,
        agentCount: agents.length,
        taskCount: 0,
        completedTaskCount: 0,
      });
    }

    return () => setActiveSession(null);
  }, [session, agents.length, setActiveSession]);

  const fetchSession = async () => {
    try {
      const res = await fetch(`/api/debate/sessions/${sessionId}`);
      const data = await res.json();
      setSession(data.session);
      setAgents(data.agents || []);
      setMessages(data.messages || []);
      setCurrentRound(data.session.current_round || 0);
      lastMsgCountRef.current = data.messages?.length || 0;
    } catch (e) {
      console.error('[Debate] Failed to fetch session:', e);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const startDebate = async () => {
    try {
      await fetch(`/api/debate/sessions/${sessionId}/start`, { method: 'POST' });
    } catch (e) {
      console.error('[Debate] Failed to start debate:', e);
    }
  };

  const getAgentAvatar = (role: string) => {
    const avatars: Record<string, string> = {
      proponent: '✅',
      opponent: '❌',
      moderator: '🎯',
      reporter: '📝',
    };
    return avatars[role] || '🤖';
  };

  const getAgentName = (role: string) => {
    const names: Record<string, string> = {
      proponent: '正方',
      opponent: '反方',
      moderator: '主持人',
      reporter: '汇报员',
    };
    return names[role] || role;
  };

  const getRoleColor = (role: string) => {
    const colors: Record<string, string> = {
      proponent: 'border-green-400 bg-green-50 text-green-700',
      opponent: 'border-red-400 bg-red-50 text-red-700',
      moderator: 'border-amber-400 bg-amber-50 text-amber-700',
      reporter: 'border-blue-400 bg-blue-50 text-blue-700',
    };
    return colors[role] || 'border-gray-300 bg-gray-50 text-gray-700';
  };

  const groupedMessages = messages.reduce((groups: RoundGroup[], msg) => {
    const lastGroup = groups[groups.length - 1];
    if (lastGroup && lastGroup.round === msg.round) {
      lastGroup.messages.push(msg);
    } else {
      groups.push({ round: msg.round || 1, messages: [msg] });
    }
    return groups;
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50">
        <div className="text-center p-8 bg-white rounded-xl shadow-lg">
          <div className="w-12 h-12 mx-auto mb-4 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin"></div>
          <p className="text-slate-600">加载辩论会话...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-slate-50">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center gap-3 py-3 px-4 border-b border-slate-200 bg-white">
        <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-xl flex items-center justify-center text-xl text-white shadow-md">
          💬
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="font-bold text-lg truncate text-slate-800">{session?.title || '辩论'}</h2>
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span>第 {currentRound || session?.current_round || 0} / {session?.max_rounds || 5} 轮</span>
            <span className={cn(
              'px-2 py-0.5 rounded-full text-xs font-medium',
              session?.status === 'active' ? 'bg-emerald-100 text-emerald-700 animate-pulse' :
              session?.status === 'completed' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'
            )}>
              {session?.status === 'active' ? '进行中' :
               session?.status === 'completed' ? '已完成' : '待开始'}
            </span>
          </div>
        </div>

        {/* View Mode Switcher */}
        <div className="flex bg-slate-100 rounded-lg p-1">
          <button
            onClick={() => setViewMode('graph')}
            className={cn(
              'px-3 py-1.5 rounded text-xs font-medium transition-all',
              viewMode === 'graph' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            )}
          >
            图谱
          </button>
          <button
            onClick={() => setViewMode('timeline')}
            className={cn(
              'px-3 py-1.5 rounded text-xs font-medium transition-all',
              viewMode === 'timeline' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            )}
          >
            时间线
          </button>
          <button
            onClick={() => setViewMode('stats')}
            className={cn(
              'px-3 py-1.5 rounded text-xs font-medium transition-all',
              viewMode === 'stats' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            )}
          >
            统计
          </button>
        </div>

        {session?.status === 'pending' && (
          <button
            onClick={startDebate}
            className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 rounded-lg text-white font-semibold shadow-md transition-all"
          >
            开始辩论
          </button>
        )}
        {onClose && (
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-500 transition-colors"
          >
            ✕
          </button>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex min-h-0">
        {/* Left Panel - Visualization */}
        <div className="w-80 border-r border-slate-200 bg-white p-2 flex flex-col">
          {viewMode === 'graph' && (
            <div className="flex-1 min-h-0 rounded-xl overflow-hidden border border-slate-200">
              <AgentGraphView
                className="h-full"
                onAgentClick={(agentId) => setActiveAgent(agentId)}
              />
            </div>
          )}
          {viewMode === 'timeline' && (
            <div className="flex-1 min-h-0 rounded-xl overflow-hidden">
              <ExecutionTimeline />
            </div>
          )}
          {viewMode === 'stats' && (
            <div className="flex-1 overflow-y-auto">
              <StatisticsPanel statistics={null} />
            </div>
          )}
        </div>

        {/* Right Panel - Messages */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Agent Cards */}
          <div className="flex-shrink-0 grid grid-cols-4 gap-3 px-4 py-3 bg-white border-b border-slate-200">
            {agents.map(agent => (
              <div
                key={agent.id}
                className={cn(
                  'px-4 py-3 rounded-xl border-2 transition-all shadow-sm',
                  activeAgent === agent.id
                    ? `${getRoleColor(agent.role)} scale-105 shadow-lg ring-2 ring-offset-2 ring-slate-200`
                    : 'border-slate-200 bg-slate-50'
                )}
              >
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{getAgentAvatar(agent.role)}</span>
                  <div className="min-w-0">
                    <div className="font-semibold text-sm truncate">{getAgentName(agent.role)}</div>
                    <div className={cn('text-xs', activeAgent === agent.id ? 'text-amber-600 font-medium animate-pulse' : 'text-slate-400')}>
                      {agent.status === 'debating' ? '发言中...' :
                       agent.status === 'ready' ? '就绪' : '等待'}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Messages Area */}
          <div className="flex-1 min-h-0 overflow-y-auto py-4 px-4">
            {messages.length === 0 ? (
              <div className="text-center text-slate-400 py-12">
                <div className="text-5xl mb-4">💬</div>
                <p className="text-lg mb-2 font-medium text-slate-600">辩论尚未开始</p>
                <p className="text-sm">点击"开始辩论"按钮启动辩论</p>
              </div>
            ) : (
              <div className="space-y-6">
                {groupedMessages.map((group, groupIndex) => (
                  <div key={groupIndex} className="space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="h-px flex-1 bg-gradient-to-r from-slate-300 to-transparent"></div>
                      <span className="text-xs font-semibold px-4 py-1.5 bg-gradient-to-r from-slate-100 to-slate-50 rounded-full text-slate-600 border border-slate-200 shadow-sm">
                        第 {group.round} 轮
                      </span>
                      <div className="h-px flex-1 bg-gradient-to-l from-slate-300 to-transparent"></div>
                    </div>

                    <div className="space-y-3 pl-4 border-l-2 border-slate-200">
                      {group.messages.map(message => (
                        <div key={message.id} className="flex gap-3">
                          <div className={cn(
                            'flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-xl border-2 shadow-sm',
                            getRoleColor(message.agent_role),
                            activeAgent === message.agent_id && 'ring-2 ring-blue-400 ring-offset-2'
                          )}>
                            {getAgentAvatar(message.agent_role)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={cn(
                                'font-semibold text-sm',
                                message.agent_role === 'proponent' ? 'text-green-600' :
                                message.agent_role === 'opponent' ? 'text-red-600' :
                                message.agent_role === 'moderator' ? 'text-amber-600' : 'text-blue-600'
                              )}>
                                {getAgentName(message.agent_role)}
                              </span>
                              <span className="text-xs text-slate-400">
                                {new Date(message.created_at).toLocaleTimeString()}
                              </span>
                            </div>
                            <div className={cn('rounded-xl px-4 py-3 border shadow-sm', getRoleColor(message.agent_role))}>
                              <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      {/* Report */}
      {report && (
        <div className="flex-shrink-0 border-t-2 border-blue-400 bg-white p-4 max-h-72 overflow-y-auto shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]">
          <h3 className="font-bold mb-3 flex items-center gap-2 text-blue-600">
            <span>📝</span> 辩论报告
          </h3>
          <div className="space-y-4 text-sm">
            <div className="bg-blue-50 rounded-xl p-4 border border-blue-100">
              <h4 className="text-blue-700 mb-2 font-semibold">📋 总结</h4>
              <p className="text-slate-700">{report.summary}</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-100">
                <h4 className="text-emerald-700 mb-2 font-semibold">✅ 正方观点</h4>
                <ul className="list-disc list-inside text-slate-700 space-y-1">
                  {report.proponent_points?.map((p, i) => (
                    <li key={i} className="text-sm">{p}</li>
                  ))}
                </ul>
              </div>
              <div className="bg-red-50 rounded-xl p-4 border border-red-100">
                <h4 className="text-red-700 mb-2 font-semibold">❌ 反方观点</h4>
                <ul className="list-disc list-inside text-slate-700 space-y-1">
                  {report.opponent_points?.map((p, i) => (
                    <li key={i} className="text-sm">{p}</li>
                  ))}
                </ul>
              </div>
            </div>
            {report.key_disagreements?.length > 0 && (
              <div className="bg-amber-50 rounded-xl p-4 border border-amber-100">
                <h4 className="text-amber-700 mb-2 font-semibold">⚡ 关键分歧</h4>
                <ul className="list-disc list-inside text-slate-700 space-y-1">
                  {report.key_disagreements.map((d, i) => (
                    <li key={i} className="text-sm">{d}</li>
                  ))}
                </ul>
              </div>
            )}
            {report.conclusion && (
              <div className="bg-purple-50 rounded-xl p-4 border border-purple-100">
                <h4 className="text-purple-700 mb-2 font-semibold">🎯 结论</h4>
                <p className="text-slate-700">{report.conclusion}</p>
              </div>
            )}
            {report.suggestions?.length > 0 && (
              <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
                <h4 className="text-slate-700 mb-2 font-semibold">💡 建议</h4>
                <ul className="list-disc list-inside text-slate-600 space-y-1">
                  {report.suggestions.map((s, i) => (
                    <li key={i} className="text-sm">{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Default export for lazy loading
export default EnhancedDebateWindow;