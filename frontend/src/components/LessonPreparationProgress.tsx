import { Check, FileSearch, Loader2, PanelsTopLeft, RefreshCw, ScanSearch, ShieldCheck } from 'lucide-react';
import type { ClassroomStartStatus } from '../lib/api';
import type { TeachingScope, WorkflowRun } from '../types/workflow';
import './LessonPreparationProgress.css';

const STEPS = [
  { icon: FileSearch, title: '读取资料单元', detail: '确认材料、教学范围与来源' },
  { icon: ScanSearch, title: '分析内容结构', detail: '映射知识点、重难点和学习目标' },
  { icon: PanelsTopLeft, title: '规划 PPT 页面', detail: '按页数和课时分配讲授节奏' },
  { icon: Loader2, title: '生成逐页内容', detail: 'PPT 文案、讲稿与互动锚点' },
  { icon: ShieldCheck, title: '结构质量校验', detail: '页数、引用、稳定 ID 和时间预算' },
];

function activeStep(status?: ClassroomStartStatus | null) {
  if (!status || status.phase === 'idle' || status.phase === 'queued') return 0;
  if (status.phase === 'blueprint_generating') return status.generated_chars && status.generated_chars > 400 ? 3 : 1;
  if (status.phase === 'failed') return 3;
  return 5;
}

/**
 * 阶段与任务文案必须与 phase 一致。
 * 真实事故：教师暂停后 phase 报 classroom_starting，而这里回落到 status.message
 * （「PPT V1 已生成，等待逐页审阅」），同屏出现「课堂运行中 + 等待审阅」两种状态。
 */
const PHASE_MESSAGE: Record<string, string> = {
  queued: '已进入执行队列',
  blueprint_generating: '正在生成逐页 PPT、讲稿与互动锚点',
  blueprint_ready: 'Lesson Blueprint 已就绪',
  awaiting_review: 'PPT V1 已生成，等待逐页审阅',
  classroom_starting: '正在创建独立 Teacher / Student Agent Session',
  classroom_running: '课堂演练进行中',
  classroom_completed: '课堂演练已完成',
};

export function LessonPreparationProgress({ run, status, onRetry }: { run: WorkflowRun; status: ClassroomStartStatus | null; onRetry?: (options?: { retry?: boolean; maxSlides?: number }) => Promise<void> }) {
  const step = activeStep(status);
  const scope: TeachingScope = run.teaching_data?.scope || { selected_point_titles: [], estimated_minutes: 45, depth: 'standard' };
  const slideTarget = Number(status?.target_slide_count || scope.ppt_slide_count || scope.estimated_minutes || 45);
  const points = (scope.selected_point_titles || run.teaching_data?.knowledge_points?.map((item: { title?: string }) => item.title).filter(Boolean) || []) as string[];
  const previews = status?.slide_previews || [];
  const closedSlideCount = Math.max(0, Number(status?.closed_slide_count || 0));
  const previewStart = Math.max(0, closedSlideCount - previews.length);
  const inClassroom = status?.phase === 'classroom_running' || status?.phase === 'classroom_completed';
  const isComplete = status?.phase === 'awaiting_review' || status?.phase === 'blueprint_ready' || inClassroom;
  const statusText = status?.phase ? PHASE_MESSAGE[status.phase] || status.message : '等待启动';
  const progressLabel = status?.phase === 'failed'
    ? '需处理'
    : isComplete
      ? `${closedSlideCount || slideTarget} / ${slideTarget}`
      : closedSlideCount
        ? `${Math.min(closedSlideCount, slideTarget)} / ${slideTarget}`
        : status?.generated_chars
          ? '生成中'
          : '等待';
  const failed = status?.phase === 'failed';
  const failureText = failed ? `${status?.message || ''} ${status?.error || ''}` : '';
  const failedOnLimit = /limit exceeded|too long/i.test(failureText);
  const failedOnTimeout = /timed out|timeout/i.test(failureText);
  const suggestedSlides = Math.max(3, Math.min(15, Math.round(slideTarget / 3)));
  const retryHint = failedOnLimit
    ? '单次输出超出桥传输上限，已修复读行限制；页数过多仍可能超时，建议减少页数重试。'
    : failedOnTimeout
      ? '模型在超时时间内没有返回完整结果，通常是页数过多；建议减少页数重试。'
      : '可原样重试；若反复失败，建议减少页数。';
  return <section className="lesson-preparation" aria-live="polite">
    <header><div><span>VISIBLE PREPARATION WORK</span><h3>{inClassroom ? '课堂演练阶段（PPT 文案已冻结）' : '资料分析与 PPT 文案生成'}</h3><p>展示真实输入、当前任务与结构化产物，不展示隐藏思维过程。实时预览只保留最近 4 页，完整页数以“已闭合”计数和最终 LessonVersion 为准。</p></div><div className={`lesson-preparation-progress ${status?.phase === 'failed' ? 'failed' : ''}`}><strong>{progressLabel}</strong><span>{statusText}</span></div></header>
    {failed && onRetry && <div className="preparation-failure"><p>{retryHint}</p><div className="preparation-failure-actions"><button type="button" className="secondary-button" onClick={() => void onRetry({ retry: true })}><RefreshCw size={13} />按原页数重试</button>{suggestedSlides < slideTarget && <button type="button" className="primary-button compact" onClick={() => void onRetry({ retry: true, maxSlides: suggestedSlides })}><RefreshCw size={13} />降为 {suggestedSlides} 页重试</button>}</div></div>}
    <div className="lesson-preparation-body">
      <ol>{STEPS.map((item, index) => { const Icon = item.icon; const done = step > index; const active = step === index; return <li className={done ? 'done' : active ? 'active' : ''} key={item.title}><span>{done ? <Check size={14} /> : <Icon className={active && index === 3 ? 'spin' : ''} size={14} />}</span><div><strong>{item.title}</strong><small>{item.detail}</small></div><em>{done ? '完成' : active ? '进行中' : '待开始'}</em></li>; })}</ol>
      <aside>
        <div className="lesson-input-summary"><div><small>资料输入</small><strong>{run.teaching_data?.document_name || '课程资料'}</strong></div><div><small>教学范围</small><strong>{points.length} 个知识点</strong></div><div><small>目标输出</small><strong>{slideTarget} 页 · {scope.estimated_minutes || 45} 分钟</strong></div></div>
        {previews.length > 0 && <div className="live-slide-previews"><header><strong>最近 {previews.length} 页实时预览</strong><span>已闭合 {closedSlideCount || previews.length} / {slideTarget} 页</span></header>{previews.map((preview, index) => <article key={`${preview.title}:${previewStart + index}`}><span>{previewStart + index + 1}</span><div><strong>{preview.title || '正在生成标题'}</strong><small>{preview.subtitle || preview.bullets?.[0] || '结构化内容已接收'}</small></div></article>)}</div>}
        <div className={`preparation-stream ${previews.length ? 'compact' : ''}`}><header><strong>DSH 实时输出</strong><span>{(status?.generated_chars || 0).toLocaleString()} 字符{status?.generation_attempt ? ` · 生成尝试 ${status.generation_attempt} 次` : ''}</span></header><pre>{status?.preview || '正在建立资料上下文，模型开始输出后将在此显示实际返回内容。'}</pre>{status?.generation_request_id && <small className="generation-request-id">请求标识：{status.generation_request_id} · 同一 run 只保存一个 V1{status.generation_attempt && status.generation_attempt > 1 ? ` · 含 ${status.generation_attempt - 1} 次结构化修复` : ''}</small>}{status?.generation_retry_reason && <small className="generation-retry-reason">自动修复原因：{status.generation_retry_reason}</small>}</div>
      </aside>
    </div>
  </section>;
}
