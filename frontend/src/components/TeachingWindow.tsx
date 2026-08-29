// TeachingWindow.tsx - 教学模拟可视化界面 (修复版)
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { TeachingSession, TeachingAgent, TeachingMessage, TeachingMessageReference } from '../types';
import { 
  downloadReportWithRetry, 
  canDownloadReport, 
  getDownloadButtonTooltip 
} from '../services/reportApi';
import { InteractionPathView } from './InteractionPath';
import { ObjectivesAssessmentView } from './Objectives';
import { QuizInterface, QuizResult } from './Quiz';
import { QuizWithQuestions, QuizResult as QuizResultType, generateQuiz, fetchQuizResults } from '../services/quizApi';
import { SupervisorCommentCard } from './SupervisorCommentCard';
import { TeacherLectureCard } from './TeacherLectureCard';

interface TeachingWindowProps {
  sessionId: string;
  onClose?: () => void;
}

// 播放速度配置
const PLAYBACK_SPEEDS = [
  { label: '1x', value: 1, delay: 2000 },
  { label: '1.5x', value: 1.5, delay: 1300 },
  { label: '2x', value: 2, delay: 1000 },
];

// Agent 类型
const AGENT_TYPES = {
  TEACHER: 'teacher',
  STUDENT: 'student',
  SUPERVISOR: 'supervisor',
} as const;

// 维度颜色映射
const DIMENSION_COLORS: Record<string, { bg: string; text: string; border: string; lightBg: string }> = {
  '教学设计': { bg: 'bg-blue-500', text: 'text-blue-700', border: 'border-blue-300', lightBg: 'bg-blue-50' },
  '讲授方式': { bg: 'bg-emerald-500', text: 'text-emerald-700', border: 'border-emerald-300', lightBg: 'bg-emerald-50' },
  '回答质量': { bg: 'bg-purple-500', text: 'text-purple-700', border: 'border-purple-300', lightBg: 'bg-purple-50' },
};

// 阶段定义 - 一轮包含的完整阶段
const PHASES = [
  { key: 'design', name: '设计教学', icon: '📐', description: '教师设计本轮教学方案' },
  { key: 'teach_knowledge', name: '讲授知识', icon: '📖', description: '教师讲解知识点' },
  { key: 'student_question', name: '学生提问', icon: '❓', description: '学生根据内容提问' },
  { key: 'teacher_answer', name: '教师回答', icon: '💬', description: '教师解答学生疑问' },
  { key: 'supervisor_comment', name: '督导点评', icon: '📋', description: '督导给出改进建议' },
];

// 清理AI生成的markdown符号，让内容更像真实讲课稿
const cleanContent = (content: string): string => {
  if (!content) return '';
  return content
    .replace(/\*\*/g, '') // 移除 **
    .replace(/##/g, '') // 移除 ##
    .replace(/###/g, '') // 移除 ###
    .replace(/#/g, '') // 移除 #
    .replace(/_{2,}/g, '') // 移除 __
    .replace(/\[|\]/g, '') // 移除 [ ]
    .replace(/\(\)/g, '') // 移除 ()
    .replace(/- /g, '• ') // 将列表符号替换为圆点
    .replace(/\d+\.\s+/g, '') // 移除数字序号
    .replace(/```[\s\S]*?```/g, '') // 移除代码块
    .replace(/`([^`]+)`/g, '$1') // 移除行内代码标记
    .replace(/^[\s\-*>]+/gm, '') // 移除行首的空白和符号
    .replace(/\n{3,}/g, '\n\n') // 将多个空行替换为两个
    .trim();
};

// 格式化讲课稿内容 - 更适合演讲的格式
const formatLectureContent = (content: string): string => {
  if (!content) return '';
  let formatted = cleanContent(content);
  
  // 添加自然的段落间距
  formatted = formatted
    .replace(/([。！？])\s*/g, '$1\n') // 在句号、感叹号、问号后换行
    .replace(/\n{3,}/g, '\n\n'); // 清理多余空行
    
  return formatted;
};

export function TeachingWindow({ sessionId, onClose }: TeachingWindowProps) {
  const [session, setSession] = useState<TeachingSession | null>(null);
  const [agents, setAgents] = useState<TeachingAgent[]>([]);
  const [messages, setMessages] = useState<TeachingMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [estimatedTime, setEstimatedTime] = useState<string>('计算中...');
  const [showProgressDetail, setShowProgressDetail] = useState(false); // 进度详情展开状态
  const [selectedIteration, setSelectedIteration] = useState<number | null>(null); // 选中的轮次
  const [tooltipData, setTooltipData] = useState<{
    visible: boolean;
    x: number;
    y: number;
    references: TeachingMessageReference[];
  }>({ visible: false, x: 0, y: 0, references: [] });
  const lastMsgCountRef = useRef(0);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // PDF下载相关状态
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [showSnackbar, setShowSnackbar] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  
  // 互动路径面板状态
  const [showInteractionPath, setShowInteractionPath] = useState(false);
  const [snackbarType, setSnackbarType] = useState<'success' | 'error' | 'info'>('info');

  // 学习目标面板状态
  const [showObjectives, setShowObjectives] = useState(false);

  // 测验相关状态
  const [showQuiz, setShowQuiz] = useState(false);
  const [showQuizResult, setShowQuizResult] = useState(false);
  const [currentQuiz, setCurrentQuiz] = useState<QuizWithQuestions | null>(null);
  const [quizResult, setQuizResult] = useState<QuizResultType | null>(null);
  const [isGeneratingQuiz, setIsGeneratingQuiz] = useState(false);
  const [quizError, setQuizError] = useState<string | null>(null);

  // 滚动引用
  const teacherScrollRef = useRef<HTMLDivElement>(null);
  const studentScrollRef = useRef<HTMLDivElement>(null);
  const supervisorScrollRef = useRef<HTMLDivElement>(null);

  // 获取会话数据
  const fetchSession = useCallback(async () => {
    try {
      const res = await fetch(`/api/teaching/sessions/${sessionId}`);
      if (!res.ok) {
        throw new Error(`HTTP error! status: ${res.status}`);
      }
      const data = await res.json();
      setSession(data.session);
      setAgents(data.agents || []);
      setMessages(data.messages || []);
      lastMsgCountRef.current = data.messages?.length || 0;
      setError(null);
    } catch (e) {
      console.error('[Teaching] Failed to fetch session:', e);
      if (e instanceof TypeError && e.message.includes('fetch')) {
        setError('无法连接到服务器，请确保后端服务已启动 (http://localhost:8000)');
      } else {
        setError(e instanceof Error ? e.message : '加载失败');
      }
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // 初始加载
  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  // 轮询更新
  useEffect(() => {
    if (!sessionId || error) return;

    intervalRef.current = setInterval(async () => {
      if (isPaused) return;

      try {
        const [sessionRes, msgRes] = await Promise.all([
          fetch(`/api/teaching/sessions/${sessionId}`),
          fetch(`/api/teaching/sessions/${sessionId}/messages`)
        ]);

        if (sessionRes.ok) {
          const sessionData = await sessionRes.json();
          setSession(prev => {
            const newSession = sessionData.session;
            if (!prev || 
                prev.status !== newSession.status ||
                prev.current_phase !== newSession.current_phase ||
                prev.current_iteration !== newSession.current_iteration) {
              return newSession;
            }
            return prev;
          });
        }

        if (msgRes.ok) {
          const msgData = await msgRes.json();
          if (msgData.messages && msgData.messages.length !== lastMsgCountRef.current) {
            setMessages(msgData.messages);
            lastMsgCountRef.current = msgData.messages.length;
            
            // 设置最新消息的agent为活跃
            const latestMsg = msgData.messages[msgData.messages.length - 1];
            if (latestMsg) {
              setActiveAgent(latestMsg.agent_id);
            }
          }
        }
      } catch (e) {
        console.error('[Teaching] Poll error:', e);
      }
    }, PLAYBACK_SPEEDS.find(s => s.value === playbackSpeed)?.delay || 2000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [sessionId, isPaused, playbackSpeed, error]);

  // 自动滚动到最新消息
  useEffect(() => {
    if (activeAgent && messages.length > 0) {
      const latestMsg = messages[messages.length - 1];
      const agent = agents.find(a => a.id === latestMsg?.agent_id);
      
      if (agent?.agent_type === AGENT_TYPES.TEACHER && teacherScrollRef.current) {
        teacherScrollRef.current.scrollTop = teacherScrollRef.current.scrollHeight;
      } else if (agent?.agent_type === AGENT_TYPES.STUDENT && studentScrollRef.current) {
        studentScrollRef.current.scrollTop = studentScrollRef.current.scrollHeight;
      } else if (agent?.agent_type === AGENT_TYPES.SUPERVISOR && supervisorScrollRef.current) {
        supervisorScrollRef.current.scrollTop = supervisorScrollRef.current.scrollHeight;
      }
    }
  }, [messages, activeAgent, agents]);

  // 计算预计剩余时间
  useEffect(() => {
    if (session && session.status === 'teaching') {
      const currentIteration = session.current_iteration || 0;
      const maxIterations = session.max_iterations || 3;
      const remainingIterations = maxIterations - currentIteration;
      
      const baseTimePerPhase = 30;
      const estimatedSeconds = remainingIterations * 5 * baseTimePerPhase / playbackSpeed;
      
      if (estimatedSeconds < 60) {
        setEstimatedTime(`约 ${Math.ceil(estimatedSeconds)} 秒`);
      } else {
        setEstimatedTime(`约 ${Math.ceil(estimatedSeconds / 60)} 分钟`);
      }
    } else if (session?.status === 'completed') {
      setEstimatedTime('已完成');
    } else {
      setEstimatedTime('待开始');
    }
  }, [session, playbackSpeed]);

  const startTeaching = async () => {
    try {
      const res = await fetch(`/api/teaching/sessions/${sessionId}/start`, { method: 'POST' });
      if (!res.ok) throw new Error('启动失败');
      setIsPaused(false);
      await fetchSession();
    } catch (e) {
      console.error('[Teaching] Failed to start teaching:', e);
      alert('启动教学失败，请重试');
    }
  };

  const togglePause = () => setIsPaused(!isPaused);

  const handleNext = async () => {
    try {
      const res = await fetch(`/api/teaching/sessions/${sessionId}/next`, { method: 'POST' });
      if (!res.ok) throw new Error('下一步失败');
      await fetchSession();
    } catch (e) {
      console.error('[Teaching] Failed to next:', e);
      alert('下一步失败，请重试');
    }
  };

  const handleReplay = async () => {
    try {
      const res = await fetch(`/api/teaching/sessions/${sessionId}/replay`, { method: 'POST' });
      if (!res.ok) throw new Error('重播失败');
      setMessages([]);
      lastMsgCountRef.current = 0;
      await fetchSession();
    } catch (e) {
      console.error('[Teaching] Failed to replay:', e);
      alert('重播失败，请重试');
    }
  };

  // 导出功能
  const exportToMarkdown = () => {
    if (!session || messages.length === 0) return;

    let markdown = `# ${session.title}\n\n`;
    markdown += `> 教学模拟记录\n`;
    markdown += `> 时间：${new Date().toLocaleString()}\n`;
    markdown += `> 迭代次数：${session.max_iterations} 轮\n\n`;
    markdown += `## 讲课稿\n\n${session.teaching_script || '暂无'}\n\n`;
    markdown += `## 教学过程\n\n`;

    let currentIteration = 0;
    messages.forEach(msg => {
      if (msg.iteration !== currentIteration) {
        currentIteration = msg.iteration;
        markdown += `\n### 第 ${currentIteration} 轮\n\n`;
      }
      markdown += `**${msg.agent_name}**：${msg.content}\n\n`;
    });

    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${session.title}_${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const exportToText = () => {
    if (!session || messages.length === 0) return;

    let text = `${session.title}\n`;
    text += `${'='.repeat(session.title.length)}\n\n`;
    
    messages.forEach(msg => {
      text += `[${msg.agent_name}]\n${msg.content}\n\n`;
    });

    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${session.title}_${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Snackbar 显示函数
  const showNotification = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setSnackbarMessage(message);
    setSnackbarType(type);
    setShowSnackbar(true);
    // 3秒后自动隐藏
    setTimeout(() => {
      setShowSnackbar(false);
    }, 3000);
  };

  // PDF导出功能
  const handleExportPdf = async () => {
    if (!session || !canDownloadReport(session.status)) {
      showNotification('教学尚未完成，无法导出报告', 'error');
      return;
    }

    setIsDownloadingPdf(true);
    setDownloadError(null);
    showNotification('正在生成PDF报告...', 'info');

    try {
      await downloadReportWithRetry(
        sessionId,
        {
          filename: `${session.title}_教学报告_${new Date().toISOString().split('T')[0]}.pdf`,
          onSuccess: () => {
            showNotification('报告下载成功！', 'success');
          },
          onError: (error) => {
            console.error('[TeachingWindow] PDF下载失败:', error);
            setDownloadError(error.message);
            showNotification(error.message, 'error');
          },
        },
        3, // 最多重试3次
        1000 // 每次间隔1秒
      );
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : '下载失败';
      setDownloadError(errorMsg);
      showNotification(errorMsg, 'error');
    } finally {
      setIsDownloadingPdf(false);
    }
  };

  // 重试下载
  const handleRetryDownload = () => {
    setDownloadError(null);
    handleExportPdf();
  };

  // 测验相关函数
  const handleStartQuiz = async () => {
    setIsGeneratingQuiz(true);
    setQuizError(null);
    try {
      const quiz = await generateQuiz(sessionId, {
        question_count: 10,
        time_limit_minutes: 30,
      });
      setCurrentQuiz(quiz);
      setShowQuiz(true);
    } catch (e) {
      setQuizError(e instanceof Error ? e.message : '生成测验失败');
    } finally {
      setIsGeneratingQuiz(false);
    }
  };

  const handleQuizSubmit = async (result: { quizId: string; score: number; maxScore: number }) => {
    setShowQuiz(false);
    try {
      const fullResult = await fetchQuizResults(result.quizId);
      setQuizResult(fullResult);
      setShowQuizResult(true);
    } catch (e) {
      setQuizError(e instanceof Error ? e.message : '获取测验结果失败');
    }
  };

  const handleQuizExit = () => {
    setShowQuiz(false);
  };

  const handleQuizRetry = () => {
    setShowQuizResult(false);
    setQuizResult(null);
    handleStartQuiz();
  };

  const handleQuizBack = () => {
    setShowQuizResult(false);
    setShowQuiz(false);
    setQuizResult(null);
    setCurrentQuiz(null);
  };

  // 按类型分组 Agents
  const groupedAgents = useMemo(() => ({
    teachers: agents.filter(a => a.agent_type === AGENT_TYPES.TEACHER),
    students: agents.filter(a => a.agent_type === AGENT_TYPES.STUDENT),
    supervisors: agents.filter(a => a.agent_type === AGENT_TYPES.SUPERVISOR),
  }), [agents]);

  // 按类型分组 Messages - 直接使用消息中的 agent_type
  const groupedMessages = useMemo(() => ({
    teacherMsgs: messages.filter(m => m.agent_type === AGENT_TYPES.TEACHER),
    studentMsgs: messages.filter(m => m.agent_type === AGENT_TYPES.STUDENT),
    supervisorMsgs: messages.filter(m => m.agent_type === AGENT_TYPES.SUPERVISOR),
  }), [messages]);

  // 按轮次分组消息
  const getMessagesByIteration = (msgs: TeachingMessage[]) => {
    // 如果选择了特定轮次，只返回该轮次的消息
    if (selectedIteration !== null) {
      const filtered = msgs.filter(m => m.iteration === selectedIteration);
      return filtered.length > 0 ? [{ iteration: selectedIteration, messages: filtered }] : [];
    }

    const groups: { iteration: number; messages: TeachingMessage[] }[] = [];
    msgs.forEach(msg => {
      const existingGroup = groups.find(g => g.iteration === msg.iteration);
      if (existingGroup) {
        existingGroup.messages.push(msg);
      } else {
        groups.push({ iteration: msg.iteration, messages: [msg] });
      }
    });
    return groups.sort((a, b) => a.iteration - b.iteration);
  };

  // 判断是否为优化内容（迭代>1即为优化轮次）
  const isOptimizedContent = (message: TeachingMessage) => {
    return message.iteration > 1;
  };

  const getAgentAvatar = (agent: TeachingAgent) => {
    if (agent.agent_type === 'teacher') return '👨‍🏫';
    if (agent.agent_type === 'supervisor') return '🔍';
    if (agent.level === 'high') return '🎓';
    if (agent.level === 'medium') return '📚';
    return '📖';
  };

  const getAgentName = (agent: TeachingAgent) => {
    if (agent.agent_type === 'teacher') return '教师';
    if (agent.agent_type === 'supervisor') return agent.name;
    if (agent.level === 'high') return '探索学生';
    if (agent.level === 'medium') return '提升学生';
    return '基础学生';
  };

  const getPhaseName = (phase: string) => {
    const found = PHASES.find(p => p.key === phase);
    return found ? `${found.icon} ${found.name}` : phase;
  };

  // 获取当前阶段索引
  const currentPhaseIndex = PHASES.findIndex(p => p.key === session?.current_phase);
  
  // 计算总进度 - 基于当前轮次和阶段
  const totalProgress = useMemo(() => {
    if (!session) return 0;
    if (session.status === 'completed') return 100;
    if (session.status === 'pending') return 0;
    
    const currentIter = session.current_iteration || 1;
    const maxIter = session.max_iterations || 3;
    const phaseIdx = currentPhaseIndex >= 0 ? currentPhaseIndex : 0;
    
    // 计算已完成的部分
    const completedIterations = currentIter - 1;
    const currentIterationProgress = (phaseIdx + 1) / PHASES.length;
    
    const progress = ((completedIterations + currentIterationProgress) / maxIter) * 100;
    return Math.min(Math.round(progress), 100);
  }, [session, currentPhaseIndex]);

  // 判断当前活跃区域
  const getActiveArea = () => {
    if (!activeAgent) return null;
    const agent = agents.find(a => a.id === activeAgent);
    return agent?.agent_type || null;
  };

  const activeArea = getActiveArea();

  // 判断当前正在生成的区域（根据 session 状态）
  const getGeneratingArea = (): 'teacher' | 'student' | 'supervisor' | null => {
    if (!session || session.status !== 'teaching') return null;
    const phase = session.current_phase;
    if (!phase) return null;
    
    if (['design', 'teach_knowledge', 'teacher_answer'].includes(phase)) {
      return 'teacher';
    } else if (phase === 'student_question') {
      return 'student';
    } else if (phase === 'supervisor_comment') {
      return 'supervisor';
    }
    return null;
  };

  const generatingArea = getGeneratingArea();

  // 错误处理
  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50 p-8">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h3 className="text-lg font-bold text-slate-800 mb-2">加载出错</h3>
          <p className="text-sm text-slate-600 mb-4">{error}</p>
          <button
            onClick={fetchSession}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            重新加载
          </button>
        </div>
      </div>
    );
  }

  // 检测损坏的会话数据
  const isCorruptedSession = session?.status === 'completed' && agents.length === 0 && messages.length === 0;
  if (isCorruptedSession) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50 p-8">
        <div className="bg-white rounded-xl shadow-lg p-8 max-w-md text-center">
          <div className="text-4xl mb-4">📭</div>
          <h3 className="text-lg font-bold text-slate-800 mb-2">会话数据不完整</h3>
          <p className="text-sm text-slate-600 mb-4">
            此教学会话被标记为"已完成"，但没有找到任何教学数据。
            这通常是因为教学过程未正常执行或数据丢失。
          </p>
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4 text-left">
            <p className="text-xs text-amber-800">
              <strong>建议：</strong>请删除此会话，重新创建一个新的教学会话。
            </p>
          </div>
          <div className="flex gap-3 justify-center">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-500 text-white rounded-lg hover:bg-slate-600 transition-colors"
            >
              返回列表
            </button>
            <button
              onClick={() => {
                if (confirm('确定要删除此会话吗？')) {
                  fetch(`/api/teaching/sessions/${sessionId}`, { method: 'DELETE' })
                    .then(() => onClose())
                    .catch(console.error);
                }
              }}
              className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
            >
              删除会话
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50">
        <div className="text-center p-8 bg-white rounded-xl shadow-lg">
          <div className="w-12 h-12 mx-auto mb-4 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin"></div>
          <p className="text-slate-600">加载教学会话...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-50 min-h-0">
      {/* Header - 顶部标题栏 */}
      <div className="flex items-center gap-4 py-3 px-4 bg-white border-b border-slate-200 shrink-0">
        <div className="w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center text-xl text-white">
          📖
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="font-bold text-base text-slate-800 truncate">{session?.title || '教学'}</h2>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="font-medium">第 {session?.current_iteration || 1} / {session?.max_iterations || 3} 轮</span>
            {session?.current_phase && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                {getPhaseName(session.current_phase)}
              </span>
            )}
            <span className="text-slate-400">⏱️ {estimatedTime}</span>
          </div>
        </div>

        {/* 控制按钮组 */}
        <div className="flex items-center gap-2">
          {/* 调试日志输出当前状态 */}
          {(() => { console.log('[TeachingWindow] 当前 session.status:', session?.status); return null; })()}
          
          {session?.status === 'teaching' && (
            <>
              <button
                onClick={togglePause}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all active:scale-95 ${
                  isPaused 
                    ? 'bg-emerald-500 hover:bg-emerald-600 text-white' 
                    : 'bg-amber-500 hover:bg-amber-600 text-white'
                }`}
              >
                {isPaused ? '▶️ 继续' : '⏸️ 暂停'}
              </button>
              
              <select
                value={playbackSpeed}
                onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                className="px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-sm cursor-pointer hover:border-slate-300"
              >
                {PLAYBACK_SPEEDS.map(speed => (
                  <option key={speed.value} value={speed.value}>{speed.label}</option>
                ))}
              </select>

              <button
                onClick={handleNext}
                className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg text-slate-700 text-sm transition-colors active:scale-95"
              >
                ⏭️ 下一步
              </button>
            </>
          )}
          
          {session?.status === 'pending' && (
            <button
              onClick={startTeaching}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-semibold rounded-lg transition-all active:scale-95"
            >
              ▶️ 开始教学
            </button>
          )}

          {session?.status === 'completed' && (
            <button
              onClick={handleReplay}
              className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg transition-all active:scale-95"
            >
              🔄 重播
            </button>
          )}

          {/* 默认按钮：当 status 不匹配任何已知状态时显示 */}
          {!['teaching', 'pending', 'completed'].includes(session?.status || '') && (
            <button
              onClick={startTeaching}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-semibold rounded-lg transition-all active:scale-95"
              title={`当前状态: ${session?.status || 'unknown'}，点击开始教学`}
            >
              ▶️ 开始教学
            </button>
          )}

          {/* 导出按钮组 */}
          {(messages.length > 0 || session?.status === 'completed') && (
            <div className="relative group">
              <button className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg text-slate-700 text-sm transition-colors flex items-center gap-1">
                <span>📥</span>
                <span>导出</span>
              </button>
              <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-slate-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                {/* PDF导出 - 仅教学完成后可用 */}
                <button
                  onClick={handleExportPdf}
                  disabled={isDownloadingPdf || !canDownloadReport(session?.status || '')}
                  title={getDownloadButtonTooltip(session?.status || '')}
                  className={`w-full px-4 py-2 text-left text-sm border-b border-slate-100 transition-colors flex items-center gap-2 ${
                    canDownloadReport(session?.status || '')
                      ? 'text-slate-700 hover:bg-slate-50'
                      : 'text-slate-400 cursor-not-allowed'
                  }`}
                >
                  {isDownloadingPdf ? (
                    <>
                      <span className="w-4 h-4 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin"></span>
                      <span>生成中...</span>
                    </>
                  ) : (
                    <>
                      <span>📄</span>
                      <span>PDF报告</span>
                    </>
                  )}
                </button>
                <button
                  onClick={exportToMarkdown}
                  className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 border-b border-slate-100 transition-colors flex items-center gap-2"
                >
                  <span>📝</span>
                  <span>Markdown</span>
                </button>
                <button
                  onClick={exportToText}
                  className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 transition-colors flex items-center gap-2"
                >
                  <span>📃</span>
                  <span>文本</span>
                </button>
              </div>
            </div>
          )}

          {onClose && (
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center bg-white border border-slate-200 hover:bg-slate-50 rounded-lg text-slate-500 transition-colors"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* 进度条 - 可点击展开详情 */}
      <div className="px-4 py-2 bg-white border-b border-slate-200 shrink-0">
        <div 
          className="cursor-pointer"
          onClick={() => setShowProgressDetail(!showProgressDetail)}
        >
          <div className="flex items-center justify-between text-xs text-slate-600 mb-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">教学进度</span>
              <span className="text-slate-400">|</span>
              <span className="text-blue-600">
                第 {session?.current_iteration || 1} 轮 · {PHASES[currentPhaseIndex]?.name || '待开始'}
              </span>
              <span className="text-slate-400 ml-1">
                {showProgressDetail ? '▲' : '▼'}
              </span>
            </div>
            <span className="font-bold text-blue-600">{totalProgress}%</span>
          </div>
          <div className="h-2.5 bg-slate-200 rounded-full overflow-hidden hover:bg-slate-300 transition-colors">
            <div 
              className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${totalProgress}%` }}
            />
          </div>
        </div>
        
        {/* 进度详情面板 - 可展开 */}
        {showProgressDetail && session && (
          <div className="mt-3 pt-3 border-t border-slate-200">
            <div className="grid grid-cols-3 gap-2">
              {Array.from({ length: session.max_iterations || 3 }, (_, i) => i + 1).map((iter) => {
                const isCurrent = iter === session.current_iteration;
                const isCompleted = iter < (session.current_iteration || 1) || session.status === 'completed';
                
                return (
                  <div
                    key={iter}
                    onClick={() => setSelectedIteration(selectedIteration === iter ? null : iter)}
                    className={`p-2 rounded-lg border-2 cursor-pointer transition-all ${
                      isCurrent
                        ? 'bg-blue-50 border-blue-500 shadow-sm'
                        : isCompleted
                        ? 'bg-emerald-50 border-emerald-300'
                        : 'bg-slate-50 border-slate-200'
                    } ${selectedIteration === iter ? 'ring-2 ring-blue-400' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-xs font-bold ${
                        isCurrent ? 'text-blue-700' : isCompleted ? 'text-emerald-700' : 'text-slate-500'
                      }`}>
                        第 {iter} 轮
                      </span>
                      {isCompleted && <span className="text-xs">✓</span>}
                      {isCurrent && <span className="text-xs animate-pulse">▶</span>}
                    </div>
                    <div className="text-xs text-slate-600">
                      {isCompleted ? '已完成' : isCurrent ? '进行中' : '待开始'}
                    </div>
                    {iter > 1 && isCompleted && (
                      <div className="mt-1 text-xs text-yellow-600">🌟 已优化</div>
                    )}
                  </div>
                );
              })}
            </div>
            
            {/* 选中轮次的详细进度 */}
            {selectedIteration && (
              <div className="mt-3 p-3 bg-slate-50 rounded-lg border border-slate-200">
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-medium text-sm text-slate-700">第 {selectedIteration} 轮进度</span>
                  {selectedIteration > 1 && (
                    <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded">
                      基于上轮督导意见优化
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-wrap">
                  {PHASES.map((phase, idx) => {
                    const phaseInIteration = messages.filter(
                      m => m.iteration === selectedIteration && m.phase === phase.key
                    );
                    const hasContent = phaseInIteration.length > 0;
                    const isCurrentPhase = selectedIteration === session.current_iteration && 
                                          session.current_phase === phase.key;
                    
                    return (
                      <div key={phase.key} className="flex items-center">
                        <div 
                          className={`px-2 py-1 rounded text-xs transition-all ${
                            isCurrentPhase
                              ? 'bg-blue-500 text-white font-medium'
                              : hasContent
                              ? 'bg-emerald-100 text-emerald-700'
                              : 'bg-slate-200 text-slate-500'
                          }`}
                          title={phase.description}
                        >
                          <span className="mr-1">{phase.icon}</span>
                          {phase.name}
                        </div>
                        {idx < PHASES.length - 1 && (
                          <span className="mx-1 text-slate-400">→</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            
            <div className="mt-2 text-xs text-slate-500 text-center">
              点击轮次卡片查看详情，再次点击关闭
            </div>
          </div>
        )}
      </div>

      {/* 暂停提示 */}
      {isPaused && session?.status === 'teaching' && (
        <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 shrink-0">
          <div className="flex items-center justify-center gap-2 text-amber-700 text-sm">
            <span>⏸️</span>
            <span className="font-medium">教学已暂停</span>
            <button 
              onClick={togglePause}
              className="ml-4 px-3 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded text-xs transition-colors"
            >
              继续
            </button>
          </div>
        </div>
      )}

      {/* 轮次导航器 - 显式轮次选择 */}
      <div className="px-4 py-2 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">📑 轮次导航：</span>
            <div className="flex items-center gap-1">
              {Array.from({ length: session?.max_iterations || 3 }, (_, i) => i + 1).map((iter) => {
                const isCurrent = iter === session?.current_iteration;
                const isCompleted = iter < (session?.current_iteration || 1) || session?.status === 'completed';
                const isSelected = selectedIteration === iter;
                
                return (
                  <button
                    key={iter}
                    onClick={() => setSelectedIteration(selectedIteration === iter ? null : iter)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                      isSelected
                        ? 'bg-blue-500 text-white shadow-md'
                        : isCurrent
                        ? 'bg-blue-100 text-blue-700 border-2 border-blue-400'
                        : isCompleted
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100'
                        : 'bg-slate-50 text-slate-500 border border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      {isCompleted && !isCurrent && <span className="text-xs">✓</span>}
                      {isCurrent && !isSelected && <span className="text-xs animate-pulse">▶</span>}
                      {isSelected && <span className="text-xs">👁</span>}
                      第 {iter} 轮
                    </span>
                  </button>
                );
              })}
            </div>
            {selectedIteration && (
              <button
                onClick={() => setSelectedIteration(null)}
                className="ml-2 px-2 py-1 text-xs text-slate-500 hover:text-slate-700 bg-slate-100 hover:bg-slate-200 rounded transition-colors"
              >
                显示全部
              </button>
            )}
          </div>
          <div className="text-xs text-slate-500">
            {selectedIteration ? (
              <span className="text-blue-600 font-medium">正在查看第 {selectedIteration} 轮内容</span>
            ) : (
              <span>点击轮次按钮筛选内容</span>
            )}
          </div>
        </div>
      </div>

      {/* 三栏布局主体 - 根据互动路径面板调整高度 */}
      <div className={`flex min-h-0 overflow-hidden ${showInteractionPath ? 'h-[65%]' : 'flex-1'}`}>
        
        {/* 教师区域 - 35% */}
        <div className="w-[35%] flex flex-col bg-blue-50 border-r-2 border-blue-300">
          {/* 区域标题 */}
          <div className="px-4 py-2 bg-blue-100 border-b border-blue-200 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-lg">👨‍🏫</span>
              <span className="font-bold text-blue-800">教师区域</span>
              <span className="text-xs text-blue-600">({groupedAgents.teachers.length}人)</span>
            </div>
            {generatingArea === 'teacher' && (
              <span className="px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-ping"></span>
                正在输入...
              </span>
            )}
            {activeArea === 'teacher' && generatingArea !== 'teacher' && (
              <span className="px-2 py-0.5 bg-blue-500 text-white text-xs font-bold rounded-full animate-pulse">
                发言中
              </span>
            )}
          </div>
          
          {/* Agent 列表 */}
          <div className="px-3 py-2 bg-blue-50 border-b border-blue-100 shrink-0">
            <div className="flex flex-wrap gap-2">
              {groupedAgents.teachers.map(agent => (
                <div
                  key={agent.id}
                  className={`flex items-center gap-1 px-2 py-1 rounded border text-sm transition-all ${
                    activeAgent === agent.id
                      ? 'bg-blue-200 border-blue-400 shadow-sm'
                      : 'bg-white border-blue-200'
                  }`}
                >
                  <span>{getAgentAvatar(agent)}</span>
                  <span className="font-medium text-blue-700">{getAgentName(agent)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 消息区域 */}
          <div ref={teacherScrollRef} className="flex-1 overflow-y-auto p-3 space-y-4">
            {groupedMessages.teacherMsgs.length === 0 ? (
              <div className="text-center py-8 text-blue-400">
                <div className="text-2xl mb-2">📝</div>
                <p className="text-sm">等待教师发言...</p>
                <p className="text-xs text-blue-300 mt-1">每轮教师都会重新讲解并优化</p>
              </div>
            ) : (
              getMessagesByIteration(groupedMessages.teacherMsgs).map((group) => (
                <div key={group.iteration} className="space-y-3">
                  {/* 轮次标记 */}
                  <div className="flex items-center gap-2 py-2">
                    <div className="flex-1 h-px bg-blue-300"></div>
                    <span className={`text-xs font-bold px-3 py-1 rounded-full shadow-sm ${
                      group.iteration > 1 
                        ? 'bg-yellow-200 text-yellow-800 border border-yellow-300' 
                        : 'bg-blue-100 text-blue-600 border border-blue-200'
                    }`}>
                      {group.iteration > 1 ? '🌟 第' : '📖 第'} {group.iteration} 轮{group.iteration > 1 ? '（优化版）' : '（初稿）'}
                    </span>
                    <div className="flex-1 h-px bg-blue-300"></div>
                  </div>
                  {/* 消息 - 讲课稿样式 */}
                  {group.messages.map((message) => {
                    const agent = agents.find(a => a.id === message.agent_id);
                    const isOptimized = isOptimizedContent(message);
                    const isDesignPhase = message.phase === 'design';
                    const isTeachPhase = message.phase === 'teach_knowledge' || message.phase === 'teacher_answer';
                    
                    return (
                      <div
                        key={message.id}
                        className={`rounded-lg border-2 shadow-sm transition-all overflow-hidden ${
                          isOptimized 
                            ? 'bg-gradient-to-br from-yellow-50 to-white border-yellow-400' 
                            : 'bg-white border-blue-200'
                        } ${isTeachPhase ? 'border-l-4 border-l-blue-500' : ''}`}
                      >
                        {/* 消息头部 */}
                        <div className={`px-3 py-2 flex items-center gap-2 ${
                          isDesignPhase ? 'bg-blue-100' : 
                          isTeachPhase ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white' : 
                          'bg-slate-100'
                        }`}>
                          <span className="text-lg" title={agent?.agent_type === 'teacher' ? '教师' : agent?.agent_type || '未知'}>
                            {agent ? getAgentAvatar(agent) : '👨‍🏫'}
                          </span>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className={`text-xs font-bold ${isTeachPhase ? 'text-white' : 'text-blue-700'}`}>
                                {message.agent_name}
                              </span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${isTeachPhase ? 'bg-blue-400 text-white' : 'bg-blue-200 text-blue-700'}`}>
                                教师
                              </span>
                            </div>
                            <span className={`text-xs ${isTeachPhase ? 'text-blue-100' : 'text-slate-500'}`}>
                              {isDesignPhase ? '📐 教学设计' : isTeachPhase ? '📖 讲课内容' : '💬 教师回复'}
                            </span>
                          </div>
                          <span className={`text-xs ${isTeachPhase ? 'text-blue-100' : 'text-slate-400'}`}>
                            {new Date(message.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                        
                        {/* 消息内容 - 讲课稿格式 */}
                        <div className="p-4">
                          {isDesignPhase ? (
                            // 教学设计 - 结构化展示
                            <div className="space-y-2">
                              <div className="text-xs text-slate-500 mb-2">本节课的教学设计方案：</div>
                              <div className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed pl-3 border-l-2 border-blue-300">
                                {formatLectureContent(message.content)}
                              </div>
                            </div>
                          ) : isTeachPhase ? (
                            // 讲课内容 - 使用卡片组件
                            <TeacherLectureCard
                              content={message.content}
                              iteration={message.iteration}
                              isOptimized={isOptimized}
                            />
                          ) : (
                            // 其他内容
                            <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                              {cleanContent(message.content)}
                            </p>
                          )}
                        </div>
                        
                        {/* 优化溯源区域 */}
                        {isOptimized && isTeachPhase && message.references && message.references.length > 0 && (
                          <div className="px-4 py-3 bg-yellow-50 border-t border-yellow-200">
                            <div className="text-xs font-medium text-yellow-800 mb-2">💡 优化溯源</div>
                            <div className="space-y-2">
                              {message.references.map((ref, refIdx) => {
                                const colors = DIMENSION_COLORS[ref.dimension] || DIMENSION_COLORS['教学设计'];
                                const suggestionSummary = ref.suggestion.length > 30 
                                  ? ref.suggestion.substring(0, 30) + '...' 
                                  : ref.suggestion;
                                return (
                                  <div
                                    key={refIdx}
                                    className="flex items-start gap-2 cursor-pointer group"
                                    onMouseEnter={(e) => {
                                      const rect = (e.target as HTMLElement).getBoundingClientRect();
                                      setTooltipData({
                                        visible: true,
                                        x: rect.left,
                                        y: rect.bottom + 8,
                                        references: message.references || []
                                      });
                                    }}
                                    onMouseLeave={() => {
                                      setTooltipData(prev => ({ ...prev, visible: false }));
                                    }}
                                  >
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors.lightBg} ${colors.text} border ${colors.border} shrink-0`}>
                                      {ref.dimension}
                                    </span>
                                    <span className="text-xs text-yellow-700 group-hover:text-yellow-800 transition-colors">
                                      借鉴{ref.agent_name}的建议：{suggestionSummary}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                        
                        {/* 优化标记（无references时显示） */}
                        {isOptimized && isTeachPhase && (!message.references || message.references.length === 0) && (
                          <div className="px-4 py-2 bg-yellow-50 border-t border-yellow-200">
                            <div className="flex items-center gap-2">
                              <span className="text-yellow-600">💡</span>
                              <span className="text-xs text-yellow-700 font-medium">
                                本讲内容已根据第 {group.iteration - 1} 轮督导建议进行优化
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </div>

        {/* 学生区域 - 30% */}
        <div className="w-[30%] flex flex-col bg-emerald-50 border-r-2 border-emerald-300">
          {/* 区域标题 */}
          <div className="px-4 py-2 bg-emerald-100 border-b border-emerald-200 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-lg">👥</span>
              <span className="font-bold text-emerald-800">学生区域</span>
              <span className="text-xs text-emerald-600">({groupedAgents.students.length}人)</span>
            </div>
            {generatingArea === 'student' && (
              <span className="px-2 py-0.5 bg-emerald-500 text-white text-xs font-bold rounded-full animate-pulse flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-ping"></span>
                正在输入...
              </span>
            )}
            {activeArea === 'student' && generatingArea !== 'student' && (
              <span className="px-2 py-0.5 bg-emerald-500 text-white text-xs font-bold rounded-full animate-pulse">
                发言中
              </span>
            )}
          </div>
          
          {/* Agent 列表 */}
          <div className="px-3 py-2 bg-emerald-50 border-b border-emerald-100 shrink-0">
            <div className="flex flex-wrap gap-2">
              {groupedAgents.students.map(agent => (
                <div
                  key={agent.id}
                  className={`flex items-center gap-1 px-2 py-1 rounded border text-sm transition-all ${
                    activeAgent === agent.id
                      ? 'bg-emerald-200 border-emerald-400 shadow-sm'
                      : 'bg-white border-emerald-200'
                  }`}
                >
                  <span>{getAgentAvatar(agent)}</span>
                  <span className="font-medium text-emerald-700">{getAgentName(agent)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 消息区域 */}
          <div ref={studentScrollRef} className="flex-1 overflow-y-auto p-3 space-y-4">
            {groupedMessages.studentMsgs.length === 0 ? (
              <div className="text-center py-8 text-emerald-400">
                <div className="text-2xl mb-2">📚</div>
                <p className="text-sm">等待学生提问...</p>
                <p className="text-xs text-emerald-300 mt-1">每轮根据教学内容提问</p>
              </div>
            ) : (
              getMessagesByIteration(groupedMessages.studentMsgs).map((group) => (
                <div key={group.iteration} className="space-y-3">
                  {/* 轮次标记 */}
                  <div className="flex items-center gap-2 py-2">
                    <div className="flex-1 h-px bg-emerald-300"></div>
                    <span className="text-xs font-bold text-emerald-600 bg-emerald-100 px-3 py-1 rounded-full border border-emerald-200">
                      第 {group.iteration} 轮提问
                    </span>
                    <div className="flex-1 h-px bg-emerald-300"></div>
                  </div>
                  {/* 消息 */}
                  {group.messages.map((message) => {
                    const agent = agents.find(a => a.id === message.agent_id);
                    const isQuestion = message.phase === 'student_question';
                    
                    return (
                      <div
                        key={message.id}
                        className="rounded-lg border-2 bg-white border-emerald-200 shadow-sm overflow-hidden"
                      >
                        {/* 消息头部 */}
                        <div className={`px-3 py-2 flex items-center gap-2 ${
                          isQuestion ? 'bg-emerald-500 text-white' : 'bg-emerald-100'
                        }`}>
                          <span className="text-lg" title={agent?.agent_type === 'student' ? '学生' : agent?.agent_type || '未知'}>
                            {agent ? getAgentAvatar(agent) : '📖'}
                          </span>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className={`text-xs font-bold ${isQuestion ? 'text-white' : 'text-emerald-700'}`}>
                                {message.agent_name}
                              </span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${isQuestion ? 'bg-emerald-400 text-white' : 'bg-emerald-200 text-emerald-700'}`}>
                                学生
                              </span>
                            </div>
                            <span className={`text-xs ${isQuestion ? 'text-emerald-100' : 'text-emerald-600'}`}>
                              {isQuestion ? '❓ 提出问题' : '💬 学生发言'}
                            </span>
                          </div>
                        </div>
                        
                        {/* 消息内容 */}
                        <div className="p-3">
                          {isQuestion ? (
                            <div className="space-y-2">
                              <div className="flex items-start gap-2">
                                <span className="text-emerald-500 text-lg">❓</span>
                                <p className="text-sm text-slate-800 leading-relaxed flex-1">
                                  {cleanContent(message.content)}
                                </p>
                              </div>
                            </div>
                          ) : (
                            <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                              {cleanContent(message.content)}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </div>

        {/* 督导区域 - 35% */}
        <div className="w-[35%] flex flex-col bg-orange-50">
          {/* 区域标题 */}
          <div className="px-4 py-2 bg-orange-100 border-b border-orange-200 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2">
              <span className="text-lg">🔍</span>
              <span className="font-bold text-orange-800">督导区域</span>
              <span className="text-xs text-orange-600">({groupedAgents.supervisors.length}人)</span>
            </div>
            {generatingArea === 'supervisor' && (
              <span className="px-2 py-0.5 bg-orange-500 text-white text-xs font-bold rounded-full animate-pulse flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-white rounded-full animate-ping"></span>
                正在输入...
              </span>
            )}
            {activeArea === 'supervisor' && generatingArea !== 'supervisor' && (
              <span className="px-2 py-0.5 bg-orange-500 text-white text-xs font-bold rounded-full animate-pulse">
                发言中
              </span>
            )}
          </div>
          
          {/* Agent 列表 */}
          <div className="px-3 py-2 bg-orange-50 border-b border-orange-100 shrink-0">
            <div className="flex flex-wrap gap-2">
              {groupedAgents.supervisors.map(agent => (
                <div
                  key={agent.id}
                  className={`flex items-center gap-1 px-2 py-1 rounded border text-sm transition-all ${
                    activeAgent === agent.id
                      ? 'bg-orange-200 border-orange-400 shadow-sm'
                      : 'bg-white border-orange-200'
                  }`}
                >
                  <span>{getAgentAvatar(agent)}</span>
                  <span className="font-medium text-orange-700">{getAgentName(agent)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 消息区域 */}
          <div ref={supervisorScrollRef} className="flex-1 overflow-y-auto p-3 space-y-4">
            {groupedMessages.supervisorMsgs.length === 0 ? (
              <div className="text-center py-8 text-orange-400">
                <div className="text-2xl mb-2">📋</div>
                <p className="text-sm">等待督导点评...</p>
                <p className="text-xs text-orange-300 mt-1">每轮给出改进建议</p>
              </div>
            ) : (
              getMessagesByIteration(groupedMessages.supervisorMsgs).map((group) => (
                <div key={group.iteration} className="space-y-3">
                  {/* 轮次标记 */}
                  <div className="flex items-center gap-2 py-2">
                    <div className="flex-1 h-px bg-orange-300"></div>
                    <span className="text-xs font-bold text-orange-600 bg-orange-100 px-3 py-1 rounded-full border border-orange-200">
                      第 {group.iteration} 轮督导
                    </span>
                    <div className="flex-1 h-px bg-orange-300"></div>
                  </div>
                  {/* 消息 */}
                  {group.messages.map((message) => {
                    const agent = agents.find(a => a.id === message.agent_id);
                    const isComment = message.phase === 'supervisor_comment';
                    // 从 references 或 content 中解析维度信息
                    const dimensions = message.references?.map(r => r.dimension) || [];
                    // 如果没有 references，尝试从内容中推断维度（基于关键词）
                    const inferredDimensions: string[] = [];
                    if (dimensions.length === 0 && message.content) {
                      const content = message.content.toLowerCase();
                      if (content.includes('设计') || content.includes('结构') || content.includes('安排')) {
                        inferredDimensions.push('教学设计');
                      }
                      if (content.includes('讲授') || content.includes('讲解') || content.includes('表达') || content.includes('语速')) {
                        inferredDimensions.push('讲授方式');
                      }
                      if (content.includes('回答') || content.includes('解答') || content.includes('答疑')) {
                        inferredDimensions.push('回答质量');
                      }
                    }
                    const displayDimensions = dimensions.length > 0 ? dimensions : inferredDimensions;
                    
                    return (
                      <div
                        key={message.id}
                        className="rounded-lg border-2 bg-white border-orange-200 shadow-sm overflow-hidden"
                      >
                        {/* 消息头部 */}
                        <div className={`px-3 py-2 flex items-center gap-2 ${
                          isComment ? 'bg-orange-500 text-white' : 'bg-orange-100'
                        }`}>
                          <span className="text-lg" title={agent?.agent_type === 'supervisor' ? '督导' : agent?.agent_type || '未知'}>
                            {agent ? getAgentAvatar(agent) : '🔍'}
                          </span>
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className={`text-xs font-bold ${isComment ? 'text-white' : 'text-orange-700'}`}>
                                {message.agent_name}
                              </span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${isComment ? 'bg-orange-400 text-white' : 'bg-orange-200 text-orange-700'}`}>
                                督导
                              </span>
                            </div>
                            <span className={`text-xs ${isComment ? 'text-orange-100' : 'text-orange-600'}`}>
                              {isComment ? '📋 督导点评' : '💡 督导建议'}
                            </span>
                          </div>
                          <span className={`text-xs ${isComment ? 'text-orange-100' : 'text-slate-400'}`}>
                            {new Date(message.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                        
                        {/* 消息内容 */}
                        <div className="p-3">
                          {isComment ? (
                            <SupervisorCommentCard
                              content={message.content}
                              agentName={message.agent_name}
                              iteration={message.iteration}
                              createdAt={message.created_at}
                            />
                          ) : (
                            <div>
                              {/* 维度标签 */}
                              {displayDimensions.length > 0 && (
                                <div className="flex flex-wrap gap-1.5 mb-2">
                                  {displayDimensions.map((dim, idx) => {
                                    const colors = DIMENSION_COLORS[dim] || DIMENSION_COLORS['教学设计'];
                                    return (
                                      <span
                                        key={idx}
                                        className={`px-2 py-0.5 rounded text-xs font-medium ${colors.bg} text-white`}
                                      >
                                        {dim}
                                      </span>
                                    );
                                  })}
                                </div>
                              )}
                              <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                                {cleanContent(message.content)}
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Tooltip - 悬浮显示完整建议 */}
      {tooltipData.visible && tooltipData.references.length > 0 && (
        <div
          className="fixed z-50 max-w-md bg-white rounded-lg shadow-xl border border-slate-200 p-4 pointer-events-none"
          style={{ left: Math.min(tooltipData.x, window.innerWidth - 400), top: tooltipData.y }}
        >
          <div className="text-sm font-bold text-slate-800 mb-3">📋 督导建议详情</div>
          <div className="space-y-3">
            {Array.from(new Set(tooltipData.references.map(r => r.dimension))).map(dimension => {
              const colors = DIMENSION_COLORS[dimension] || DIMENSION_COLORS['教学设计'];
              const dimensionRefs = tooltipData.references.filter(r => r.dimension === dimension);
              return (
                <div key={dimension} className={`p-3 rounded-lg ${colors.lightBg} border ${colors.border}`}>
                  <div className={`text-xs font-bold ${colors.text} mb-2`}>{dimension}</div>
                  <div className="space-y-2">
                    {dimensionRefs.map((ref, idx) => (
                      <div key={idx} className="text-xs text-slate-700">
                        <span className="font-medium">{ref.agent_name}:</span> {ref.suggestion}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Snackbar - 状态提示 */}
      {showSnackbar && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50">
          <div
            className={`px-6 py-3 rounded-lg shadow-lg flex items-center gap-3 transition-all duration-300 ${
              snackbarType === 'success'
                ? 'bg-emerald-500 text-white'
                : snackbarType === 'error'
                ? 'bg-red-500 text-white'
                : 'bg-slate-800 text-white'
            }`}
          >
            {snackbarType === 'success' && <span>✅</span>}
            {snackbarType === 'error' && <span>❌</span>}
            {snackbarType === 'info' && (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
            )}
            <span className="font-medium">{snackbarMessage}</span>
            {snackbarType === 'error' && downloadError && (
              <button
                onClick={handleRetryDownload}
                className="ml-2 px-3 py-1 bg-white/20 hover:bg-white/30 rounded text-sm transition-colors"
              >
                重试
              </button>
            )}
            <button
              onClick={() => setShowSnackbar(false)}
              className="ml-2 text-white/70 hover:text-white transition-colors"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* 阶段指示器 - 底部 */}
      <div className="px-4 py-3 bg-white border-t border-slate-200 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center justify-center gap-1 flex-wrap flex-1">
            {PHASES.map((phase, index) => {
              const isActive = session?.current_phase === phase.key;
              const isCompleted = currentPhaseIndex > index || session?.status === 'completed';
              
              return (
                <div key={phase.key} className="flex items-center">
                  <div 
                    className={`flex flex-col items-center px-2 py-2 rounded-lg border-2 transition-all cursor-pointer hover:shadow-md ${
                      isActive
                        ? 'bg-blue-100 border-blue-500 text-blue-700'
                        : isCompleted
                        ? 'bg-slate-100 border-slate-300 text-slate-600'
                        : 'bg-white border-slate-200 text-slate-400'
                    }`}
                    title={phase.description}
                  >
                    <span className="text-lg">{phase.icon}</span>
                    <span className="text-xs font-medium whitespace-nowrap">{phase.name}</span>
                    {isActive && <span className="text-xs animate-pulse">💬</span>}
                  </div>
                  {index < PHASES.length - 1 && (
                    <span className="mx-1 text-slate-400">→</span>
                  )}
                </div>
              );
            })}
          </div>
          
          {/* 学习目标按钮 */}
          <button
            onClick={() => setShowObjectives(!showObjectives)}
            className={`ml-4 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors flex items-center gap-1.5 ${
              showObjectives
                ? 'bg-indigo-500 text-white hover:bg-indigo-600'
                : 'bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-700'
            }`}
          >
            <span>🎯</span>
            <span>学习目标</span>
            {showObjectives && <span className="text-xs">▼</span>}
          </button>

          {/* 互动路径按钮 */}
          {(messages.length > 0 || session?.status === 'completed') && (
            <button
              onClick={() => setShowInteractionPath(!showInteractionPath)}
              className={`ml-2 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors flex items-center gap-1.5 ${
                showInteractionPath
                  ? 'bg-purple-500 text-white hover:bg-purple-600'
                  : 'bg-purple-50 hover:bg-purple-100 border border-purple-200 text-purple-700'
              }`}
            >
              <span>🔍</span>
              <span>互动路径</span>
              {showInteractionPath && <span className="text-xs">▼</span>}
            </button>
          )}

          {/* 知识点测验按钮 */}
          {session?.status === 'completed' && (
            <button
              onClick={handleStartQuiz}
              disabled={isGeneratingQuiz}
              className={`ml-2 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors flex items-center gap-1.5 ${
                showQuiz || showQuizResult
                  ? 'bg-emerald-500 text-white hover:bg-emerald-600'
                  : 'bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-emerald-700'
              }`}
            >
              {isGeneratingQuiz ? (
                <>
                  <span className="w-4 h-4 border-2 border-emerald-300 border-t-emerald-500 rounded-full animate-spin"></span>
                  <span>生成中...</span>
                </>
              ) : (
                <>
                  <span>📝</span>
                  <span>知识点测验</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* 互动路径面板 */}
      {showInteractionPath && (
        <div className="h-[35%] border-t border-slate-200 bg-white flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 bg-purple-50 border-b border-purple-200">
            <div className="flex items-center gap-2">
              <span className="text-lg">🔍</span>
              <span className="font-bold text-purple-800">互动路径可视化</span>
            </div>
            <button
              onClick={() => setShowInteractionPath(false)}
              className="p-1.5 hover:bg-purple-100 rounded-lg text-purple-600 transition-colors"
            >
              <span className="text-lg">✕</span>
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <InteractionPathView sessionId={sessionId} />
          </div>
        </div>
      )}

      {/* 学习目标面板 */}
      {showObjectives && (
        <div className="h-[45%] border-t border-slate-200 bg-white flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 bg-indigo-50 border-b border-indigo-200">
            <div className="flex items-center gap-2">
              <span className="text-lg">🎯</span>
              <span className="font-bold text-indigo-800">学习目标匹配度评估</span>
            </div>
            <button
              onClick={() => setShowObjectives(false)}
              className="p-1.5 hover:bg-indigo-100 rounded-lg text-indigo-600 transition-colors"
            >
              <span className="text-lg">✕</span>
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <ObjectivesAssessmentView sessionId={sessionId} />
          </div>
        </div>
      )}

      {/* 测验界面 */}
      {showQuiz && currentQuiz && (
        <div className="fixed inset-0 z-50 bg-slate-50">
          <QuizInterface
            quiz={currentQuiz}
            onSubmit={handleQuizSubmit}
            onExit={handleQuizExit}
          />
        </div>
      )}

      {/* 测验结果界面 */}
      {showQuizResult && quizResult && currentQuiz && (
        <div className="fixed inset-0 z-50 bg-slate-50">
          <QuizResult
            result={quizResult}
            quiz={currentQuiz}
            onRetry={handleQuizRetry}
            onBack={handleQuizBack}
          />
        </div>
      )}

      {/* 测验错误提示 */}
      {quizError && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50">
          <div className="px-6 py-3 bg-red-500 text-white rounded-lg shadow-lg flex items-center gap-3">
            <span>❌</span>
            <span>{quizError}</span>
            <button
              onClick={() => setQuizError(null)}
              className="ml-2 text-white/70 hover:text-white"
            >
              ✕
            </button>
          </div>
        </div>
      )}

    </div>
  );
}

// Default export for lazy loading
export default TeachingWindow;
