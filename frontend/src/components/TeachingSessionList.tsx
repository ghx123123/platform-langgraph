// TeachingSessionList.tsx - 教学会话列表 - 明亮主题
import { useState, useEffect } from 'react';
import { TeachingSession } from '../types';

interface TeachingSessionListProps {
  onSelectSession: (sessionId: string) => void;
  onCreateNew: () => void;
}

export function TeachingSessionList({ onSelectSession, onCreateNew }: TeachingSessionListProps) {
  const [sessions, setSessions] = useState<TeachingSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch('/api/teaching/sessions');
      if (!res.ok) {
        throw new Error(`服务器返回错误: ${res.status} ${res.statusText}`);
      }
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (e) {
      console.error('[TeachingSessionList] Failed to fetch:', e);
      if (e instanceof TypeError && e.message.includes('fetch')) {
        setError('无法连接到服务器，请确保后端服务已启动');
      } else {
        setError(e instanceof Error ? e.message : '获取失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const deleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('确定要删除这个教学会话吗？')) return;
    
    try {
      const res = await fetch(`/api/teaching/sessions/${sessionId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        setSessions(sessions.filter(s => s.id !== sessionId));
      }
    } catch (e) {
      console.error('[TeachingSessionList] Failed to delete:', e);
    }
  };

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { text: string; className: string }> = {
      'pending': { 
        text: '待开始', 
        className: 'bg-slate-100 text-slate-600 border border-slate-200' 
      },
      'teaching': { 
        text: '进行中', 
        className: 'bg-emerald-100 text-emerald-700 border border-emerald-200' 
      },
      'completed': { 
        text: '已完成', 
        className: 'bg-blue-100 text-blue-700 border border-blue-200' 
      },
      'error': { 
        text: '错误', 
        className: 'bg-red-100 text-red-700 border border-red-200' 
      },
    };
    const badge = badges[status] || { 
      text: status, 
      className: 'bg-slate-100 text-slate-600 border border-slate-200' 
    };
    return (
      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${badge.className}`}>
        {badge.text}
      </span>
    );
  };

  const getStatusIcon = (status: string) => {
    const icons: Record<string, string> = {
      'pending': '⏳',
      'teaching': '▶️',
      'completed': '✅',
      'error': '❌',
    };
    return icons[status] || '📖';
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center p-12 bg-white/80 backdrop-blur-sm rounded-3xl shadow-xl">
          <div className="w-16 h-16 mx-auto mb-6 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin"></div>
          <p className="text-slate-600 font-medium">加载会话列表...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center p-12 bg-white/80 backdrop-blur-sm rounded-3xl shadow-xl">
          <div className="w-20 h-20 mx-auto mb-6 bg-red-100 rounded-full flex items-center justify-center">
            <span className="text-4xl">⚠️</span>
          </div>
          <p className="text-red-600 font-medium mb-4">{error}</p>
          <button
            onClick={fetchSessions}
            className="px-6 py-3 bg-gradient-to-r from-blue-500 to-indigo-600 text-white font-medium rounded-xl shadow-lg hover:shadow-xl transition-all duration-300"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden p-6">
      {/* Header Card */}
      <div className="max-w-5xl mx-auto mb-8">
        <div className="bg-white/80 backdrop-blur-sm rounded-3xl shadow-lg border border-slate-200/60 p-8">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-3xl font-bold text-slate-800 mb-2 flex items-center gap-3">
                <span className="w-12 h-12 bg-gradient-to-br from-violet-500 to-purple-600 rounded-2xl flex items-center justify-center text-2xl shadow-lg">
                  📖
                </span>
                教学模拟
              </h2>
              <p className="text-slate-500">
                共 <span className="font-semibold text-slate-700">{sessions.length}</span> 个会话
                {sessions.length > 0 && (
                  <span className="ml-2">
                    · {sessions.filter(s => s.status === 'teaching').length} 进行中
                  </span>
                )}
              </p>
            </div>
            <button
              onClick={onCreateNew}
              className="px-8 py-4 bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-600 hover:to-purple-700 text-white font-semibold rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 hover:-translate-y-1 flex items-center gap-2"
            >
              <span className="text-xl">+</span>
              <span>新建教学</span>
            </button>
          </div>
        </div>
      </div>

      {/* Session Grid */}
      <div className="max-w-5xl mx-auto overflow-y-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
        {sessions.length === 0 ? (
          <div className="text-center p-16 bg-white/80 backdrop-blur-sm rounded-3xl shadow-xl border border-slate-200/60">
            <div className="w-28 h-28 mx-auto mb-8 bg-gradient-to-br from-violet-100 to-purple-100 rounded-3xl flex items-center justify-center">
              <span className="text-6xl">📖</span>
            </div>
            <h3 className="text-2xl font-bold text-slate-800 mb-3">还没有教学会话</h3>
            <p className="text-slate-500 mb-8 text-lg">
              上传文档，创建你的第一个教学模拟
            </p>
            <button
              onClick={onCreateNew}
              className="px-8 py-4 bg-gradient-to-r from-violet-500 to-purple-600 hover:from-violet-600 hover:to-purple-700 text-white font-semibold rounded-2xl shadow-lg hover:shadow-2xl transition-all duration-300 hover:-translate-y-1"
            >
              <span className="mr-2">📖</span>新建教学
            </button>
          </div>
        ) : (
          <div className="grid gap-5">
            {sessions.map((session, index) => (
              <div
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-md border border-slate-200/60 p-6 cursor-pointer transition-all duration-300 hover:shadow-xl hover:-translate-y-1 hover:border-violet-300 group"
                style={{ animationDelay: `${index * 0.05}s` }}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-4 mb-3">
                      <div className="w-14 h-14 bg-gradient-to-br from-slate-100 to-slate-200 rounded-xl flex items-center justify-center text-2xl shadow-sm">
                        {getStatusIcon(session.status)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-xl text-slate-800 truncate mb-1">
                          {session.title}
                        </h3>
                        <div className="flex items-center gap-3 text-sm text-slate-500">
                          <span className="flex items-center gap-1">
                            <span>📅</span>
                            {new Date(session.created_at).toLocaleDateString()}
                          </span>
                          {session.document_id && (
                            <span className="flex items-center gap-1">
                              <span>📄</span>
                              已关联文档
                            </span>
                          )}
                        </div>
                      </div>
                      {getStatusBadge(session.status)}
                    </div>
                    
                    <div className="flex items-center gap-6 mt-4 ml-[72px]">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-slate-400">进度</span>
                        <div className="w-32 h-2 bg-slate-200 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-violet-500 to-purple-600 rounded-full transition-all duration-500"
                            style={{ 
                              width: `${((session.current_iteration || 0) / (session.max_iterations || 1)) * 100}%` 
                            }}
                          />
                        </div>
                        <span className="font-semibold text-slate-700">
                          {session.current_iteration || 0} / {session.max_iterations} 轮
                        </span>
                      </div>
                      
                      {session.status === 'teaching' && session.current_phase && (
                        <span className="text-sm font-medium text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full">
                          当前: {getPhaseName(session.current_phase)}
                        </span>
                      )}
                    </div>
                    
                    {session.teaching_script && (
                      <p className="mt-4 ml-[72px] text-sm text-slate-500 line-clamp-2 bg-slate-50 p-3 rounded-xl">
                        {getTeachingScriptPreview(session.teaching_script)}
                      </p>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-2 ml-4 opacity-0 group-hover:opacity-100 transition-all duration-300">
                    <button
                      onClick={(e) => deleteSession(session.id, e)}
                      className="p-3 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all duration-200"
                      title="删除会话"
                    >
                      <span className="text-xl">🗑️</span>
                    </button>
                    <div className="w-10 h-10 bg-gradient-to-r from-violet-500 to-purple-600 rounded-xl flex items-center justify-center text-white shadow-lg">
                      <span className="text-lg">→</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// 解析讲课稿预览文本
function getTeachingScriptPreview(teachingScript: string | null | undefined): string | null {
  if (!teachingScript) return null;

  // 尝试解析 JSON
  try {
    const parsed = JSON.parse(teachingScript);
    // 如果是 JSON，提取课程主题作为预览
    if (parsed.course_overview?.topic) {
      return `课程: ${parsed.course_overview.topic}`;
    }
    if (parsed.knowledge_points && parsed.knowledge_points.length > 0) {
      return `知识点: ${parsed.knowledge_points[0]?.name || '已设计'}`;
    }
    return '教学内容已设计';
  } catch {
    // 不是 JSON，是普通文本
    const cleanText = teachingScript
      .replace(/```[\s\S]*?```/g, '') // 移除代码块
      .replace(/[#*_[\]()]/g, '') // 移除格式符号
      .trim();
    return cleanText.substring(0, 100);
  }
}

function getPhaseName(phase: string): string {
  const names: Record<string, string> = {
    'design': '设计教学',
    'teach_knowledge': '讲授知识',
    'student_question': '学生提问',
    'teacher_answer': '教师回答',
    'supervisor_comment': '督导点评',
  };
  return names[phase] || phase;
}

// Default export for lazy loading
export default TeachingSessionList;
