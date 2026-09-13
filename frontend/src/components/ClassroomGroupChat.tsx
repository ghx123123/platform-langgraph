import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { MessageCircle, Send, ShieldCheck } from 'lucide-react';
import type { ClassroomEvent } from '../types/workflow';
import './ClassroomGroupChat.css';

type ClassroomStatus = 'active' | 'paused' | 'completed' | 'stopped' | 'failed' | string | undefined;

interface ClassroomGroupChatProps {
  events: ClassroomEvent[];
  activeAgentId?: string | null;
  status?: ClassroomStatus;
  canIntervene: boolean;
  sending?: boolean;
  onIntervene?: (content: string, options?: { intent: InterventionIntent; scope: InterventionScope }) => Promise<void>;
}

type ActorKey = 'teacher' | 'student-high' | 'student-medium' | 'student-low' | 'user' | 'system';

/** 介入意图: 提问只回答; 纠正改内容(会改课件); 要求约束后续行为 */
export type InterventionIntent = 'question' | 'correct' | 'require';
/** 介入范围: 本页 / 本轮剩余 / 整节课 */
export type InterventionScope = 'slide' | 'round' | 'lesson';

const INTENT_OPTIONS: Array<{ value: InterventionIntent; label: string; hint: string }> = [
  { value: 'question', label: '提问', hint: '只回答这一次，不影响后续' },
  { value: 'correct', label: '纠正', hint: '纠正内容，会改到下一版课件' },
  { value: 'require', label: '要求', hint: '约束后续课堂行为，如多提问' },
];

const SCOPE_OPTIONS: Array<{ value: InterventionScope; label: string }> = [
  { value: 'slide', label: '本页' },
  { value: 'round', label: '本轮剩余' },
  { value: 'lesson', label: '整节课' },
];

const INTENT_LABELS: Record<InterventionIntent, string> = { question: '提问', correct: '纠正', require: '要求' };
const SCOPE_LABELS: Record<InterventionScope, string> = { slide: '本页', round: '本轮', lesson: '整节课' };

interface ActorPresentation {
  key: ActorKey;
  label: string;
  short: string;
}

const ACTION_LABELS: Record<string, string> = {
  'classroom.teacher.explanation': '讲解',
  'classroom.teacher.question': '提问',
  'classroom.teacher.followup': '追问',
  'classroom.teacher.feedback': '反馈',
  'classroom.teacher.answer': '答疑',
  'classroom.teacher.summary': '总结',
  'classroom.student.answer': '回答',
  'classroom.student.question': '提问',
  'classroom.student.clarification': '补充',
  'classroom.student.silence': '未作答',
  'classroom.user.intervention': '课堂介入',
};

const SYSTEM_COPY: Record<string, (event: ClassroomEvent) => string> = {
  'classroom.round.started': () => '课堂演练开始',
  'classroom.round.completed': () => '本轮课堂演练完成',
  'classroom.round.paused': () => '课堂已暂停',
  'classroom.round.resumed': () => '课堂继续',
  'classroom.round.stopped': () => '课堂已停止',
  'classroom.slide.entered': event => `进入新一页：${event.content || event.slide_id || ''}`,
  'classroom.slide.completed': event => `本页讲授完成：${event.content || event.slide_id || ''}`,
  'classroom.agent.error': () => '智能体本轮响应异常，课堂已按降级策略继续',
};

const MEMBERS = [
  { id: 'teacher', key: 'teacher', short: '师', label: '教师' },
  { id: 'student:high', key: 'student-high', short: '拓', label: '拓展型' },
  { id: 'student:medium', key: 'student-medium', short: '进', label: '进阶型' },
  { id: 'student:low', key: 'student-low', short: '基', label: '基础型' },
] as const;

function formatTime(seconds = 0) {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`;
}

function actorFor(event: ClassroomEvent): ActorPresentation {
  if (event.event_type === 'classroom.agent.error') return { key: 'system', label: '课堂系统', short: '系' };
  if (event.actor_role === 'user' || event.event_type === 'classroom.user.intervention') {
    return { key: 'user', label: '我', short: '我' };
  }
  if (event.actor_role === 'teacher') return { key: 'teacher', label: '教师 Agent', short: '师' };
  if (event.actor_role !== 'student') return { key: 'system', label: '课堂系统', short: '系' };
  const id = event.actor_id.toLowerCase();
  if (id.includes('high') || id.includes('student a') || id.endsWith(':a')) {
    return { key: 'student-high', label: '拓展型学生', short: '拓' };
  }
  if (id.includes('medium') || id.includes('student b') || id.endsWith(':b')) {
    return { key: 'student-medium', label: '进阶型学生', short: '进' };
  }
  return { key: 'student-low', label: '基础型学生', short: '基' };
}

function isActiveMember(memberId: string, activeAgentId?: string | null) {
  if (!activeAgentId) return false;
  if (memberId === activeAgentId) return true;
  const current = activeAgentId.toLowerCase();
  if (memberId === 'student:low') return current.includes('low') || current.includes('basic');
  return current.includes(memberId.replace('student:', ''));
}

function visibleEventContent(event: ClassroomEvent) {
  if (event.content) return event.content;
  if (event.event_type === 'classroom.student.silence') return '（暂未作答）';
  if (event.event_type === 'classroom.agent.error') return '智能体本轮未返回可用动作，课堂已按降级策略继续。';
  return '本次 Agent 动作未通过结构化校验，课堂已按降级策略继续。';
}

export function ClassroomGroupChat({ events, activeAgentId, status, canIntervene, sending = false, onIntervene }: ClassroomGroupChatProps) {
  const [draft, setDraft] = useState('');
  const [intent, setIntent] = useState<InterventionIntent>('question');
  const [scope, setScope] = useState<InterventionScope>('round');
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const shouldStickRef = useRef(true);
  const highlightTimerRef = useRef<number | undefined>();
  const inputRef = useRef<HTMLInputElement>(null);

  const visibleEvents = useMemo(() => events.filter(event => (
    event.actor_role !== 'supervisor' && event.event_type !== 'classroom.slide.completed'
  )), [events]);
  const eventById = useMemo(() => new Map(visibleEvents.map(event => [event.event_id, event])), [visibleEvents]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || !shouldStickRef.current) return;
    element.scrollTop = element.scrollHeight;
  }, [visibleEvents.length]);

  useEffect(() => () => {
    if (highlightTimerRef.current) window.clearTimeout(highlightTimerRef.current);
  }, []);

  const locateReply = (eventId: string) => {
    const target = scrollRef.current?.querySelector<HTMLElement>(`[data-event-id="${CSS.escape(eventId)}"]`);
    if (!target) return;
    target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
    setHighlightedId(eventId);
    if (highlightTimerRef.current) window.clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = window.setTimeout(() => setHighlightedId(null), 1200);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (!content || !onIntervene || !canIntervene || sending) return;
    setSubmitError(null);
    try {
      await onIntervene(content, { intent, scope });
      setDraft('');
      shouldStickRef.current = true;
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : '课堂介入失败');
    }
  };

  return <section className="classroom-chat" aria-label="课堂群聊">
    <header className="classroom-chat-head">
      <div className="classroom-chat-title"><MessageCircle size={17} /><div><strong>课堂群聊</strong><span>{visibleEvents.length ? `${visibleEvents.length} 条课堂事件` : '等待首个课堂事件'}</span></div></div>
      <div className="classroom-chat-members" aria-label="课堂成员">
        {MEMBERS.map(member => <span className={`classroom-chat-member ${member.key} ${isActiveMember(member.id, activeAgentId) ? 'active' : ''}`} key={member.id} title={`${member.label}${isActiveMember(member.id, activeAgentId) ? '，当前发言' : ''}`}>
          <b>{member.short}</b><span>{member.label}</span>
        </span>)}
        <span className="classroom-chat-member supervisor" title="督导仅旁听并记录证据"><b>督</b><span>督导 · 旁听</span><ShieldCheck size={12} /></span>
      </div>
    </header>

    <div className="classroom-chat-log" ref={scrollRef} role="log" aria-live="polite" onScroll={event => {
      const element = event.currentTarget;
      shouldStickRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 56;
    }}>
      {visibleEvents.length ? visibleEvents.map(event => {
        const actor = actorFor(event);
        const isSystem = actor.key === 'system';
        const reply = event.reply_to ? eventById.get(event.reply_to) : undefined;
        const replyActor = reply ? actorFor(reply) : undefined;
        if (isSystem) return <article className="classroom-chat-system" key={event.event_id} data-event-id={event.event_id}>
          <span><time>{formatTime(event.virtual_timestamp)}</time>{SYSTEM_COPY[event.event_type]?.(event) || event.content || ACTION_LABELS[event.event_type] || '课堂状态更新'}</span>
        </article>;
        return <article className={`classroom-chat-message ${actor.key} ${highlightedId === event.event_id ? 'highlighted' : ''}`} key={event.event_id} data-event-id={event.event_id}>
          <span className={`classroom-chat-avatar ${actor.key}`} aria-hidden="true">{actor.short}</span>
          <div className="classroom-chat-body">
            <div className="classroom-chat-meta"><strong>{actor.label}</strong><span>{ACTION_LABELS[event.event_type] || '课堂发言'}</span>{event.event_type === 'classroom.user.intervention' && <span className="classroom-chat-intent-badge">{INTENT_LABELS[(event.metadata?.intent as InterventionIntent) || 'question']} · {SCOPE_LABELS[(event.metadata?.scope as InterventionScope) || 'round']}</span>}<time>{formatTime(event.virtual_timestamp)}</time></div>
            <div className="classroom-chat-bubble">
              {reply && replyActor && <button type="button" className="classroom-chat-reply" onClick={() => locateReply(reply.event_id)} title="定位到被回复的消息">
                <strong>回复 {replyActor.label}</strong><span>{reply.content || ACTION_LABELS[reply.event_type] || '课堂事件'}</span>
              </button>}
              <p>{visibleEventContent(event)}</p>
            </div>
          </div>
        </article>;
      }) : <div className="classroom-chat-empty"><MessageCircle size={20} /><span>课堂启动后，这里将显示真实的教师讲解、学生回答与追问。</span></div>}
    </div>

    <form className="classroom-chat-compose" onSubmit={submit}>
      <label className="visually-hidden" htmlFor="classroom-intervention">介入当前课堂</label>
      <div className="classroom-chat-intervention-head">
        <strong>介入当前课堂</strong>
        <span>提交后在完整事件边界暂停，由同一 Teacher Agent 回应。</span>
      </div>
      <div className="classroom-chat-intent" role="group" aria-label="介入意图">
        {INTENT_OPTIONS.map(option => (
          <button
            type="button"
            key={option.value}
            className={intent === option.value ? 'active' : ''}
            title={option.hint}
            disabled={!canIntervene || sending}
            onClick={() => setIntent(option.value)}
          >
            {option.label}
          </button>
        ))}
        <span className="classroom-chat-intent-divider" aria-hidden="true" />
        {SCOPE_OPTIONS.map(option => (
          <button
            type="button"
            key={option.value}
            className={scope === option.value ? 'active scope' : 'scope'}
            disabled={!canIntervene || sending || intent === 'question'}
            title={intent === 'question' ? '提问不产生约束，无需选择范围' : `生效范围：${option.label}`}
            onClick={() => setScope(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="classroom-chat-quick" aria-label="快捷课堂介入">
        {[
          '请换一个更贴近学生生活的例子。',
          '请把当前概念再解释得简单一些。',
          '请先停一下，我想向教师提问。',
        ].map((item, index) => (
          <button
            type="button"
            key={item}
            disabled={!canIntervene || sending}
            onClick={() => {
              setDraft(item);
              window.requestAnimationFrame(() => inputRef.current?.focus());
            }}
          >
            {['换个例子', '重新解释', '临时提问'][index]}
          </button>
        ))}
      </div>
      <input ref={inputRef} id="classroom-intervention" name="classroom_intervention" autoComplete="off" value={draft} onChange={event => setDraft(event.target.value)} placeholder={status === 'paused' ? '课堂已暂停，可以向教师提问或提出调整意见…' : '向教师提问或提出授课调整…'} disabled={!canIntervene || sending} maxLength={1000} />
      <button type="submit" disabled={!canIntervene || sending || !draft.trim()} title="发送课堂介入"><Send size={16} /><span>{sending ? '处理中' : '发送'}</span></button>
      {submitError && <span className="classroom-chat-error" role="alert">{submitError}</span>}
    </form>
  </section>;
}
