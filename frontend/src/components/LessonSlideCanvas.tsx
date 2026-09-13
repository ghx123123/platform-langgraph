import type { LessonSlide } from '../types/workflow';
import './LessonSlideCanvas.css';

interface Props {
  slide?: LessonSlide;
  index?: number;
  total?: number;
  compact?: boolean;
  className?: string;
}

export function LessonSlideCanvas({ slide, index = 0, total = 0, compact = false, className = '' }: Props) {
  const ppt = slide?.ppt_content;
  const title = ppt?.title || slide?.title || '等待 PPT 内容';
  return <article className={`lesson-slide-canvas ${compact ? 'compact' : ''} ${className}`.trim()} aria-label={slide ? `第 ${index + 1} 页：${title}` : '暂无 PPT 页面'}>
    <div className="lesson-slide-accent" />
    <div className="lesson-slide-content">
      <span className="lesson-slide-kicker">{ppt?.subtitle || 'LESSON BLUEPRINT'}</span>
      <h3>{title}</h3>
      {(ppt?.bullets || []).length ? <ul>{ppt?.bullets?.map((bullet, bulletIndex) => <li key={`${slide?.slide_id}:bullet:${bulletIndex}`}>{bullet}</li>)}</ul> : <p className="lesson-slide-empty">当前页尚未填写内容要点</p>}
      {(ppt?.examples || []).slice(0, compact ? 1 : 2).map((example, exampleIndex) => <aside key={`${slide?.slide_id}:example:${exampleIndex}`}>{example}</aside>)}
      {!compact && (ppt?.code_blocks || []).slice(0, 1).map((block, blockIndex) => <pre key={`${slide?.slide_id}:code:${blockIndex}`}><code>{String(block.code || block.content || JSON.stringify(block, null, 2))}</code></pre>)}
    </div>
    <footer><span>{slide?.slide_id || 'draft'}</span><span>{total ? `${index + 1} / ${total}` : '-- / --'}</span></footer>
  </article>;
}
