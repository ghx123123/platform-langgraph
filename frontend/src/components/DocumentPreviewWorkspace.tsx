import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, ChevronDown, Copy, ExternalLink, FileSearch, FileText, Gauge,
  Layers3, ListChecks, Loader2, PanelsTopLeft, ScanSearch, Search, Target, TextSearch, Timer, X,
} from 'lucide-react';
import { documentApi } from '../lib/api';
import { getErrorMessage } from '../lib/api';
import type {
  DocumentExtractionReport, DocumentSection, DocumentVisualAnalysis, TeachingData, TeachingScope,
  VisualAnalysisBudget,
} from '../types/workflow';
import './DocumentPreviewWorkspace.css';

interface Props {
  documentId?: string;
  fileName: string;
  courseName: string;
  rawText: string;
  sections?: DocumentSection[];
  extractionReport?: DocumentExtractionReport;
  characterCount: number;
  processedCharacterCount?: number;
  isTruncated?: boolean;
  analysis?: TeachingData['content_analysis'];
  scope?: TeachingScope;
  onVisualEvidenceChange?: (items: DocumentVisualAnalysis[]) => void;
}

const relevanceNames = { core: '教学核心', support: '支撑内容', context: '背景参考' } as const;
type PreviewMode = 'original' | 'text';

function supportsOriginalPreview(fileName: string, documentId?: string): boolean {
  return Boolean(documentId && /\.(pdf|docx|pptx)$/i.test(fileName));
}

function fallbackSections(text: string): DocumentSection[] {
  const matches = [...text.matchAll(/^(#{1,6})\s+(.+)$/gm)];
  if (!matches.length) {
    return [{ id: 'section-1', title: '完整材料', level: 1, start_offset: 0, end_offset: text.length, character_count: text.length, preview: text.replace(/\s+/g, ' ').slice(0, 180) }];
  }
  return matches.map((match, index) => {
    const start = match.index || 0;
    const end = matches[index + 1]?.index ?? text.length;
    const content = text.slice(start, end).trim();
    return { id: `section-${index + 1}`, title: match[2].trim(), level: match[1].length, start_offset: start, end_offset: end, character_count: content.length, preview: content.split('\n').slice(1).join(' ').replace(/\s+/g, ' ').slice(0, 180) };
  });
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return <button type="button" className="document-copy" onClick={() => void navigator.clipboard.writeText(text).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1400); })} aria-label={label} title={label}>{copied ? <CheckCircle2 size={14} /> : <Copy size={14} />}{copied ? '已复制' : '复制'}</button>;
}

function visualAnalysisText(analysis: DocumentVisualAnalysis): string {
  const elements = analysis.visual_elements.map((item) => `- [${item.type}] ${item.title}：${item.description}`);
  const notes = analysis.teaching_notes.map((item) => `- ${item}`);
  const corrections = analysis.ocr_corrections.map((item) => `- ${item.recognized} → ${item.corrected}（${item.evidence}）`);
  return [
    `第 ${analysis.page_number} 页视觉复核`,
    analysis.summary,
    elements.length ? `\n视觉要素\n${elements.join('\n')}` : '',
    corrections.length ? `\nOCR 修正\n${corrections.join('\n')}` : '',
    notes.length ? `\n教学提示\n${notes.join('\n')}` : '',
  ].filter(Boolean).join('\n');
}

export function DocumentPreviewWorkspace({ documentId, fileName, courseName, rawText, sections, extractionReport, characterCount, processedCharacterCount, isTruncated, analysis, scope, onVisualEvidenceChange }: Props) {
  const outline = useMemo(() => sections?.length ? sections : fallbackSections(rawText), [rawText, sections]);
  const canPreviewOriginal = supportsOriginalPreview(fileName, documentId);
  const isPresentation = /\.pptx$/i.test(fileName);
  const isPdf = /\.pdf$/i.test(fileName);
  const [selectedId, setSelectedId] = useState(outline[0]?.id || '');
  const [query, setQuery] = useState('');
  const [previewMode, setPreviewMode] = useState<PreviewMode>(() => canPreviewOriginal ? 'original' : 'text');
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');
  const [previewPageSettling, setPreviewPageSettling] = useState(false);
  const [visualAnalyses, setVisualAnalyses] = useState<DocumentVisualAnalysis[]>([]);
  const [visualBudget, setVisualBudget] = useState<VisualAnalysisBudget>('normal');
  const [visualLoading, setVisualLoading] = useState(false);
  const [visualError, setVisualError] = useState('');
  const [visualElapsed, setVisualElapsed] = useState(0);
  const coverage = analysis?.document_coverage;
  const insights = analysis?.section_insights || [];
  const insightBySection = useMemo(() => new Map(insights.map((item) => [item.section_id, item])), [insights]);

  useEffect(() => {
    setSelectedId(outline[0]?.id || '');
    setQuery('');
    setPreviewMode(canPreviewOriginal ? 'original' : 'text');
  }, [canPreviewOriginal, fileName, outline]);

  useEffect(() => {
    if (!canPreviewOriginal || !documentId) {
      setPreviewUrl('');
      setPreviewError('');
      setPreviewLoading(false);
      return;
    }
    const controller = new AbortController();
    let objectUrl = '';
    setPreviewLoading(true);
    setPreviewError('');
    void fetch(documentApi.previewUrl(documentId), { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const body = await response.json().catch(() => null) as { detail?: string } | null;
          throw new Error(body?.detail || `原页预览生成失败（${response.status}）`);
        }
        return response.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setPreviewError(reason instanceof Error ? reason.message : '原页预览生成失败');
      })
      .finally(() => {
        if (!controller.signal.aborted) setPreviewLoading(false);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [canPreviewOriginal, documentId]);

  useEffect(() => {
    setVisualAnalyses([]);
    setVisualError('');
    if (!documentId || !canPreviewOriginal) {
      onVisualEvidenceChange?.([]);
      return;
    }
    let active = true;
    void documentApi.visualAnalyses(documentId)
      .then(({ items }) => {
        if (!active) return;
        setVisualAnalyses(items);
        onVisualEvidenceChange?.(items);
      })
      .catch(() => {
        if (active) onVisualEvidenceChange?.([]);
      });
    return () => { active = false; };
  }, [canPreviewOriginal, documentId, onVisualEvidenceChange]);

  useEffect(() => {
    if (!visualLoading) return;
    setVisualElapsed(0);
    const started = Date.now();
    const interval = window.setInterval(() => setVisualElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(interval);
  }, [visualLoading]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return outline;
    return outline.filter((section) => `${section.title}\n${section.preview}`.toLowerCase().includes(keyword));
  }, [outline, query]);
  const selected = outline.find((section) => section.id === selectedId) || filtered[0] || outline[0];
  const selectedInsight = selected ? insightBySection.get(selected.id) : undefined;
  const sectionText = selected ? rawText.slice(selected.start_offset, selected.end_offset).trim() : '';
  const processed = processedCharacterCount ?? rawText.length;
  const selectedIndex = selected ? outline.indexOf(selected) : 0;
  const previewPage = selected?.page_start || (isPresentation ? Math.max(1, selectedIndex + 1) : null);
  const previewSource = previewUrl ? `${previewUrl}${previewPage ? `#page=${previewPage}&zoom=page-width` : '#zoom=page-width'}` : '';
  const currentVisualAnalysis = previewPage
    ? visualAnalyses.find((item) => item.page_number === previewPage)
    : undefined;

  const analyzeCurrentPage = async () => {
    if (!documentId || !previewPage || visualLoading) return;
    setVisualLoading(true);
    setVisualError('');
    try {
      const result = await documentApi.analyzePage(documentId, {
        page_number: previewPage,
        budget: visualBudget,
        extracted_text: sectionText.slice(0, 6000),
      });
      const next = [...visualAnalyses.filter((item) => item.page_number !== result.page_number), result]
        .sort((left, right) => left.page_number - right.page_number);
      setVisualAnalyses(next);
      onVisualEvidenceChange?.(next);
    } catch (reason) {
      setVisualError(getErrorMessage(reason));
    } finally {
      setVisualLoading(false);
    }
  };

  useEffect(() => {
    if (!previewSource) {
      setPreviewPageSettling(false);
      return;
    }
    setPreviewPageSettling(true);
    const timeout = window.setTimeout(() => setPreviewPageSettling(false), isPresentation ? 7000 : 900);
    return () => window.clearTimeout(timeout);
  }, [isPresentation, previewSource]);

  return (
    <section className="document-workspace" aria-label="课程材料预览">
      <header className="document-toolbar">
        <div className="document-identity"><FileText size={19} /><div><span>课程材料</span><strong>{courseName || fileName}</strong><small>{fileName}</small></div></div>
        <div className="document-toolbar-actions">
          {canPreviewOriginal && <div className="preview-switch" role="tablist" aria-label="材料预览方式"><button type="button" className={previewMode === 'original' ? 'active' : ''} onClick={() => setPreviewMode('original')} role="tab" aria-selected={previewMode === 'original'}><PanelsTopLeft size={14} />原页</button><button type="button" className={previewMode === 'text' ? 'active' : ''} onClick={() => setPreviewMode('text')} role="tab" aria-selected={previewMode === 'text'}><TextSearch size={14} />提取文本</button></div>}
          <div className="document-stats"><span>{outline.length}<small>分区</small></span><span>{processed.toLocaleString()}<small>已处理字符</small></span><CopyButton text={rawText} label="复制全部材料" /></div>
        </div>
      </header>

      {extractionReport && (
        <details className={`extraction-report quality-${extractionReport.quality_level}`}>
          <summary>
            <div className="extraction-score"><Gauge size={17} /><strong>{extractionReport.quality_score}</strong><span>解析质量</span></div>
            <div className="extraction-overview"><strong>{extractionReport.format} · {extractionReport.page_count ? `${extractionReport.page_count} 页` : '页数未知'}</strong><span>{extractionReport.title_count} 标题 · {extractionReport.table_count} 表格 · {extractionReport.image_count} 图片</span></div>
            <span className="extraction-level">{extractionReport.quality_level === 'high' ? '结构可靠' : extractionReport.quality_level === 'medium' ? '建议复核' : '需要复核'}</span>
            <ChevronDown size={15} />
          </summary>
          <div className="extraction-details"><span>解析引擎：{extractionReport.engine}</span><span>文本块：{extractionReport.text_block_count}</span><span>疑似扫描页：{extractionReport.scanned_page_count}</span>{extractionReport.ocr_page_count ? <span className="ocr-confirmed">页面 OCR：{extractionReport.ocr_page_count} 页</span> : null}{extractionReport.page_reports?.length ? <span className="ocr-confirmed">逐页记录：{extractionReport.page_reports.filter((page) => page.character_count > 0).length}/{extractionReport.page_reports.length} 页</span> : null}{extractionReport.ocr_image_count ? <span className="ocr-confirmed">图片 OCR：{extractionReport.ocr_image_count} 张</span> : null}{extractionReport.warnings.length ? <ul>{extractionReport.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p><CheckCircle2 size={13} />未发现明显结构风险</p>}</div>
        </details>
      )}

      {coverage ? (
        <div className="coverage-band" aria-label="文档分析覆盖情况">
          <div className="coverage-score"><CheckCircle2 size={18} /><strong>{coverage.coverage_percent}%</strong><span>结构扫描覆盖</span></div>
          <div className="coverage-method"><span>{coverage.method}</span><small>已检查 {coverage.analyzed_sections}/{coverage.total_sections} 个分区，深读 {coverage.focused_sections} 个教学核心分区</small></div>
          <div className="coverage-legend"><span className="core">{coverage.focused_sections} 核心</span><span className="support">{coverage.support_sections} 支撑</span><span className="context">{coverage.context_sections} 背景</span></div>
        </div>
      ) : (
        <div className="coverage-band pending"><div className="coverage-score"><FileSearch size={18} /><strong>待分析</strong><span>已完成结构预览</span></div><div className="coverage-method"><span>启动后将逐区扫描并回写分析覆盖</span><small>当前教学范围：{scope?.selected_point_titles.length || 0} 个知识点</small></div></div>
      )}
      {isTruncated && <div className="document-warning"><AlertTriangle size={14} />原文共 {characterCount.toLocaleString()} 字符，本次按系统上限处理前 {processed.toLocaleString()} 字符。</div>}

      <div className="document-browser">
        <aside className="document-outline">
          <div className="outline-heading"><div><Layers3 size={15} /><strong>内容目录</strong></div><small>{filtered.length}/{outline.length}</small></div>
          <label className="document-search"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题或摘要" aria-label="搜索材料分区" />{query && <button type="button" onClick={() => setQuery('')} aria-label="清空搜索"><X size={13} /></button>}</label>
          <nav className="outline-list" aria-label="文档分区">
            {filtered.map((section, index) => {
              const insight = insightBySection.get(section.id);
              const pageLabel = section.page_start ? ` · 第 ${section.page_start}${section.page_end && section.page_end !== section.page_start ? `-${section.page_end}` : ''} 页` : '';
              return <button type="button" key={section.id} className={`${selected?.id === section.id ? 'active' : ''} relevance-${insight?.relevance || 'pending'}`} onClick={() => setSelectedId(section.id)} style={{ '--section-level': Math.min(section.level - 1, 3) } as React.CSSProperties}><span>{index + 1}</span><div><strong>{section.title}</strong><small>{section.character_count.toLocaleString()} 字{pageLabel}{insight ? ` · ${relevanceNames[insight.relevance]}` : ''}</small></div>{insight?.status === 'analyzed' && <CheckCircle2 size={13} />}</button>;
            })}
            {!filtered.length && <div className="outline-empty">没有匹配的分区</div>}
          </nav>
        </aside>

        {previewMode === 'original' && canPreviewOriginal ? (
          <article className="document-reader original-reader">
            <header className="reader-heading"><div><span>{previewPage ? `第 ${previewPage} / ${extractionReport?.page_count || outline.length} 页` : '原始版式预览'}</span><h2>{selected?.title || fileName}</h2></div><div className="reader-actions"><label className="visual-budget" title="视觉复核清晰度"><span>清晰度</span><select value={visualBudget} onChange={(event) => setVisualBudget(event.target.value as VisualAnalysisBudget)} disabled={visualLoading}><option value="small">快速</option><option value="normal">标准</option><option value="large">精细</option></select></label><button type="button" className="visual-review-button" onClick={() => void analyzeCurrentPage()} disabled={!previewPage || visualLoading} title="使用当前视觉模型复核本页图表、公式与漏字"><ScanSearch size={15} />{visualLoading ? `${visualElapsed} 秒` : currentVisualAnalysis ? '重新复核' : '视觉复核本页'}</button>{documentId && <a className="document-open-original" href={documentApi.previewUrl(documentId)} target="_blank" rel="noreferrer" title="在新窗口打开原页" aria-label="在新窗口打开原页"><ExternalLink size={16} /></a>}</div></header>
            {visualLoading && <div className="visual-review-status" role="status"><Loader2 className="spin" size={16} /><div><strong>正在复核第 {previewPage} 页</strong><span>页面光栅化 → 动态分辨率对齐 → 视觉模型提取教学证据</span></div><em><Timer size={12} />{visualElapsed} 秒</em></div>}
            {!visualLoading && visualError && <div className="visual-review-status error"><AlertTriangle size={16} /><div><strong>本页视觉复核未完成</strong><span>{visualError}</span></div></div>}
            {!visualLoading && currentVisualAnalysis && <details className="visual-review-result" key={`${currentVisualAnalysis.page_number}-${currentVisualAnalysis.analyzed_at}`} open><summary><div><ScanSearch size={15} /><strong>第 {currentVisualAnalysis.page_number} 页视觉证据</strong><span>{currentVisualAnalysis.model} · {(currentVisualAnalysis.response_ms / 1000).toFixed(1)} 秒 · 置信度 {Math.round(currentVisualAnalysis.confidence * 100)}%</span></div><CopyButton text={visualAnalysisText(currentVisualAnalysis)} label="复制本页视觉复核" /><ChevronDown size={14} /></summary><div className="visual-review-content"><p>{currentVisualAnalysis.summary || '模型未补充页面摘要。'}</p>{currentVisualAnalysis.warnings.length > 0 && <div className="visual-result-warnings"><AlertTriangle size={13} /><span>{currentVisualAnalysis.warnings.join('；')}</span></div>}{currentVisualAnalysis.visual_elements.length > 0 && <section><h3><Layers3 size={13} />视觉要素</h3><ul>{currentVisualAnalysis.visual_elements.map((item, index) => <li key={`${item.type}-${index}`}><strong>{item.title}</strong><span>{item.description}</span></li>)}</ul></section>}{currentVisualAnalysis.ocr_corrections.length > 0 && <section><h3><TextSearch size={13} />文字修正</h3><ul>{currentVisualAnalysis.ocr_corrections.map((item, index) => <li key={`${item.corrected}-${index}`}><strong>{item.recognized || '漏识别'} → {item.corrected}</strong><span>{item.evidence}</span></li>)}</ul></section>}{currentVisualAnalysis.teaching_notes.length > 0 && <section><h3><ListChecks size={13} />备课提示</h3><ul>{currentVisualAnalysis.teaching_notes.map((item, index) => <li key={`${item}-${index}`}><span>{item}</span></li>)}</ul></section>}</div></details>}
            <div className="original-preview-stage" aria-live="polite">
              {previewLoading && <div className="original-preview-status"><Loader2 className="spin" size={24} /><strong>正在生成原页预览</strong><span>{/\.(docx|pptx)$/i.test(fileName) ? '首次打开需要转换版式，完成后会自动缓存。' : '正在载入课程材料。'}</span></div>}
              {!previewLoading && previewError && <div className="original-preview-status error"><AlertTriangle size={24} /><strong>原页预览暂不可用</strong><span>{previewError}</span><button type="button" className="secondary-button" onClick={() => setPreviewMode('text')}><TextSearch size={14} />查看提取文本</button></div>}
              {!previewLoading && !previewError && previewSource && <iframe key={previewSource} src={previewSource} title={`${fileName} 原页预览`} />}
              {!previewLoading && !previewError && previewSource && previewPageSettling && <div className="original-preview-status preview-settling"><Loader2 className="spin" size={22} /><strong>正在定位原页</strong><span>{isPresentation ? `正在载入第 ${previewPage} 页幻灯片。` : isPdf && previewPage ? `正在载入教材第 ${previewPage} 页。` : '正在恢复原始版式。'}</span></div>}
            </div>
          </article>
        ) : (
          <article className="document-reader">
            {selected ? <>
              <header className="reader-heading"><div><span>第 {selectedIndex + 1} / {outline.length} 区</span><h2>{selected.title}</h2></div><CopyButton text={sectionText} label="复制当前分区" /></header>
              {selectedInsight && <div className={`section-evidence relevance-${selectedInsight.relevance}`}><div><Target size={15} /><strong>{relevanceNames[selectedInsight.relevance]}</strong></div><p>{selectedInsight.evidence}</p>{selectedInsight.matched_points.length > 0 && <ul>{selectedInsight.matched_points.map((point) => <li key={point}>{point}</li>)}</ul>}</div>}
              <pre className="document-text">{sectionText}</pre>
            </> : <div className="document-reader-empty"><FileSearch size={22} /><span>请选择一个分区查看</span></div>}
          </article>
        )}
      </div>
    </section>
  );
}
