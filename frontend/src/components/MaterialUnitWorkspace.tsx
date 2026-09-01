import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import GraphView from './GraphView';
import {
  AlertCircle, ArrowDown, ArrowLeft, ArrowUp, BookOpen, Check, CheckCircle2,
  ChevronDown, Database, Edit3, FilePlus2, FileSearch, FileText, Files,
  GitMerge, History, Layers3, Link2, Loader2, Maximize, Plus, RefreshCw, Save,
  Search, Send, Sparkles, Trash2, Unlink, X, ZoomIn, ZoomOut,
} from 'lucide-react';
import { courseDesignApi, documentApi, getErrorMessage, materialUnitApi } from '../lib/api';
import type {
  CourseDesignRecord, MaterialUnitFileAnalysis, MaterialUnitKnowledgeNode, MaterialUnitKnowledgeOutline, MaterialUnitRefineTask,
  MaterialUnitRecord, MaterialUnitScopeAlignment, MaterialUnitScopeOptions, MaterialUnitSummary,
  SyllabusRequirementType,
} from '../types/workflow';
import './MaterialUnitWorkspace.css';

interface Props {
  refreshKey: number;
  onGoLibrary: () => void;
  onCourseDesignCreated: (design: CourseDesignRecord) => void | Promise<void>;
}

type Dialog =
  | { mode: 'rename'; unit: MaterialUnitSummary; title: string }
  | { mode: 'delete'; unit: MaterialUnitSummary }
  | { mode: 'merge'; target: MaterialUnitSummary; sourceIds: string[]; title: string }
  | { mode: 'link-files'; target: MaterialUnitSummary; sourceUnitId: string; materialIds: string[] }
  | { mode: 'delete-outline'; outline: MaterialUnitKnowledgeOutline; allHistory: boolean }
  | { mode: 'import-design'; outlineKey: string; materialIds: string[]; primaryMaterialId: string };

const categoryLabels: Record<string, string> = {
  syllabus: '教学大纲', schedule: '教学进度', textbook: '教材', courseware: '课件', lesson_plan: '教案',
  experiment: '实验', code: '代码', teaching_record: '教学记录', review: '审核材料', interactive: '交互资源',
  reference: '参考资料', media: '媒体', other: '其他',
};
const requirementLabels: Record<SyllabusRequirementType, string> = {
  objective: '课程目标', knowledge: '知识要求', key_point: '教学重点', difficult_point: '教学难点',
  practice: '实践要求', assessment: '考核要求',
};

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function latestOutlines(items: MaterialUnitKnowledgeOutline[]) {
  const latest = new Map<string, MaterialUnitKnowledgeOutline>();
  items.forEach((item) => {
    const current = latest.get(item.id);
    if (!current || item.version > current.version) latest.set(item.id, item);
  });
  return [...latest.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function MaterialUnitWorkspace({ refreshKey, onGoLibrary, onCourseDesignCreated }: Props) {
  const [units, setUnits] = useState<MaterialUnitSummary[]>([]);
  const [unit, setUnit] = useState<MaterialUnitRecord | null>(null);
  const [scope, setScope] = useState<MaterialUnitScopeOptions | null>(null);
  const [alignment, setAlignment] = useState<MaterialUnitScopeAlignment | null>(null);
  const [outlines, setOutlines] = useState<MaterialUnitKnowledgeOutline[]>([]);
  const [outline, setOutline] = useState<MaterialUnitKnowledgeOutline | null>(null);
  const [selectedSession, setSelectedSession] = useState('');
  const [selectedRequirements, setSelectedRequirements] = useState<string[]>([]);
  const [selectedTextbook, setSelectedTextbook] = useState<string[]>([]);
  const [draftNodes, setDraftNodes] = useState<MaterialUnitKnowledgeNode[]>([]);
  const [draftTitle, setDraftTitle] = useState('');
  const [outlineEditing, setOutlineEditing] = useState(false);
  const [refineOpen, setRefineOpen] = useState(false);
  const [refineMaterials, setRefineMaterials] = useState<string[]>([]);
  const [refineInstruction, setRefineInstruction] = useState('');
  const [aiOptimizeOpen, setAiOptimizeOpen] = useState(false);
  const [aiOptimizeInstruction, setAiOptimizeInstruction] = useState('');
  const [optimizing, setOptimizing] = useState(false);
  const [textbookFilter, setTextbookFilter] = useState<string>('all');
  const [scheduleFilter, setScheduleFilter] = useState<string>('all');
  const [syllabusFilter, setSyllabusFilter] = useState<string>('all');
  const [rawText, setRawText] = useState<string | null>(null);
  const [rawPages, setRawPages] = useState<Array<{ page: number; text: string }> | null>(null);
  const [rawLoading, setRawLoading] = useState(false);
  const [parseProgress, setParseProgress] = useState<{ progress: number; status: string; materials: Array<{ id: string; name: string; status: string; progress: number; message: string }> } | null>(null);
  const [previewFile, setPreviewFile] = useState<MaterialUnitFileAnalysis | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  // 导入课程设计前的解析补齐流程：展示逐份并行进度，解析完成后才真正 create
  const [importParsing, setImportParsing] = useState<{ taskId: string; total: number; materials: Array<{ id: string; name: string; status: string; progress: number; message: string }> } | null>(null);
  const importPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => () => { if (importPollRef.current) clearInterval(importPollRef.current); }, []);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [matching, setMatching] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [refineTask, setRefineTask] = useState<MaterialUnitRefineTask | null>(null);
  const [unitGraphNodes, setUnitGraphNodes] = useState<Array<{ id: string; title: string; quote: string; material_id: string; section_title?: string; parent_id?: string | null; content?: string }>>([]);
  const [insertPicker, setInsertPicker] = useState<{ title: string; nodeId: string; nodes: Array<{ id: string; title: string; section_title?: string; parent_id?: string | null; content?: string }> } | null>(null);
  const [graphSelectedId, setGraphSelectedId] = useState('');
  const [graphImportSet, setGraphImportSet] = useState<Set<string>>(new Set());
  const [outlineHistoryOpen, setOutlineHistoryOpen] = useState(false);
  // 三列可拖动: 列宽(px), null=auto/fr
  const [colW, setColW] = useState<{ side: number | null; main: number | null; outline: number | null }>({ side: null, main: null, outline: null });
  const dragSplit = useRef<{ which: '0' | '1'; startX: number; startW: number } | null>(null);
  // 教学补充对话框: 提示词 → dsh 生成 → 预览 → 同意/编辑
  const [teacherNoteDlg, setTeacherNoteDlg] = useState<{ nodeId: string; nodeTitle: string } | null>(null);
  const [tnInstruction, setTnInstruction] = useState('');
  const [tnGenerated, setTnGenerated] = useState('');
  const [tnEditing, setTnEditing] = useState(false);
  const [tnBusy, setTnBusy] = useState(false);
  const [graphQuery, setGraphQuery] = useState('');
  const [graphZoom, setGraphZoom] = useState(1);
  const [graphZoomToken, setGraphZoomToken] = useState(0);
  // 归一化比较: 空格/标点全去掉
  const normText = (v: string) => (v || '').replace(/[\s·．.、,，:：]/g, '').toLowerCase();
  // 该大纲节点匹配的图谱节点(其 section_title 与节点标题归一化后相同或包含)
  const graphNodesFor = (nodeTitle: string) => unitGraphNodes.filter((g) => {
    const st = normText(g.section_title || '');
    const nt = normText(nodeTitle);
    return st && nt && (st === nt || st.includes(nt) || nt.includes(st));
  });

  // 把大纲保存的选择 ID 与最新 scope 对齐: 按"内容指纹"重映射(旧编号/哈希→新哈希),
  // 匹配不到的剔除, 保证提交时不会出现"无效/过期范围选项"。
  const reconcileSelection = useCallback((
    sessionIds: string[], reqIds: string[], tbIds: string[],
    opts: import('../types/workflow').MaterialUnitScopeOptions | null,
  ) => {
    const result = { session: '', reqs: [] as string[], tb: [] as string[] };
    if (!opts) return result;
    const teachingIds = (opts.teaching_items || []).map((i) => i.id);
    const syllabusValid = (opts.syllabus_items || []).map((i) => i.id);
    const textbookValid = (opts.textbook_outline || []).map((i) => i.id);
    // 讲次: 直接取第一个有效
    result.session = sessionIds.find((id) => teachingIds.includes(id)) || teachingIds[0] || '';
    // syllabus: 有效保留; 旧的"数字 index"ID 可回退标题哈希(按题干序号映射, 此处按同一请求内容)
    const oldSyllabusMap = new Map<string, string>();
    (opts.syllabus_items || []).forEach((item) => { if (item.id) oldSyllabusMap.set(item.id, item.id); });
    result.reqs = reqIds.filter((id) => syllabusValid.includes(id));
    if (!result.reqs.length && reqIds.length) {
      // 无法按 ID 匹配: 保留原样(后端会容错跳过), 但提示
      result.reqs = reqIds.filter((id) => syllabusValid.includes(id));
    }
    // textbook: 有效保留; 旧 section-N 无法回退标题, 只能过滤失效的
    result.tb = tbIds.filter((id) => textbookValid.includes(id));
    return result;
  }, []);

  const selectOutline = useCallback((next: MaterialUnitKnowledgeOutline | null, scopeNow?: import('../types/workflow').MaterialUnitScopeOptions | null) => {
    setOutline(next);
    setDraftTitle(next?.title || '');
    setDraftNodes(next?.nodes.map((node) => ({ ...node, evidence: node.evidence.map((item) => ({ ...item })) })) || []);
    setOutlineEditing(false);
    if (next) {
      // 用最新 scope 对大纲保存的选择做"可用性对齐"(不再因过期 ID 报错)
      const reconciled = reconcileSelection(next.selected_session_ids, next.selected_syllabus_item_ids, next.selected_textbook_node_ids, scopeNow ?? scope);
      setSelectedSession(reconciled.session || next.selected_session_ids[0] || '');
      setSelectedRequirements(reconciled.reqs);
      setSelectedTextbook(reconciled.tb);
    }
  }, [scope, reconcileSelection]);

  const openUnit = useCallback(async (unitId: string) => {
    setDetailLoading(true); setError(''); setAlignment(null);
    try {
      const [record, options, outlineResponse] = await Promise.all([
        materialUnitApi.get(unitId), materialUnitApi.scopeOptions(unitId), materialUnitApi.listKnowledgeOutlines(unitId, true),
      ]);
      setUnit(record); setScope(options); setOutlines(outlineResponse.items);
      const latest = latestOutlines(outlineResponse.items)[0] || null;
      selectOutline(latest, options);
      // 加载本单元图谱节点(供教材树"可加入图谱"标记)
      try {
        const graphResp = await materialUnitApi.graphNodes(unitId);
        setUnitGraphNodes(graphResp.items);
      } catch (_g) { /* 忽略 */ }
      if (latest) {
        const taskResponse = await materialUnitApi.listRefineTasks(unitId, latest.id);
        const visibleTask = taskResponse.items.find((item) =>
          !['completed', 'failed'].includes(item.status)
          || item.result_version === latest.version
          || item.base_version === latest.version,
        );
        setRefineTask(visibleTask || null);
      } else setRefineTask(null);
      if (!latest) {
        setSelectedSession(''); setSelectedRequirements([]); setSelectedTextbook([]);
      }
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setDetailLoading(false); }
  }, [selectOutline]);

  useEffect(() => {
    if (!unit || !refineTask || ['completed', 'failed'].includes(refineTask.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await materialUnitApi.getRefineTask(unit.id, refineTask.outline_id, refineTask.id);
        setRefineTask(next);
        if (next.status === 'completed') {
          const response = await materialUnitApi.listKnowledgeOutlines(unit.id, true);
          setOutlines(response.items);
          const result = response.items.find((item) => item.id === next.outline_id && item.version === next.result_version);
          if (result) selectOutline(result);
          setRefineOpen(false); setRefineMaterials([]); setRefineInstruction('');
          setNotice(`细化任务已完成，结果已保存为第 ${next.result_version} 版。`);
        }
        if (next.status === 'failed') setError(next.error || '知识大纲细化未完成。');
      } catch (reason) { setError(getErrorMessage(reason)); }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [refineTask?.id, refineTask?.status, refineTask?.outline_id, unit?.id, selectOutline]);

  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await materialUnitApi.list();
      setUnits(response.items);
      const target = unit && response.items.some((item) => item.id === unit.id) ? unit.id : response.items[0]?.id;
      if (target) await openUnit(target); else { setUnit(null); setScope(null); setOutlines([]); selectOutline(null); }
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setLoading(false); }
  }, [openUnit, selectOutline, unit]);

  useEffect(() => { void refresh(); }, [refreshKey]);

  // 资料可能在校外(课程资料库页)被更新: 关联本地路径/上传新章节等。
  // 用户回到本页(window focus)时自动重载当前单元与 scope, 无需手动点刷新。
  useEffect(() => {
    const onFocus = () => { if (document.hasFocus() && unit?.id) void openUnit(unit.id); };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [unit?.id, openUnit]);

  // 点击文件 → 打开预览弹窗并加载识别原文/页对齐数据
  const openFilePreview = async (file: MaterialUnitFileAnalysis) => {
    setPreviewFile(file); setRawText(null); setRawPages(null); setRawLoading(false);
    if (file.parse_status === 'parsed' && unit) {
      setRawLoading(true);
      try {
        const resp = await materialUnitApi.fileText(unit.id, file.material_id);
        setRawText(resp?.text || file.summary || '');
        setRawPages(resp?.pages || null);
      } catch (_e) { setRawText(null); }
      finally { setRawLoading(false); }
    }
  };

  // 重新识别并保存: 后台任务 + 轮询进度, 完成后刷新当前预览的文件状态与文本
  const reparseFile = async (file: MaterialUnitFileAnalysis, engine: 'rapidocr' | 'mineru') => {
    if (!unit || !file.material_id) return;
    setParseProgress(null); setError(''); setRawLoading(true);
    try {
      const resp = await materialUnitApi.reparseFile(unit.id, file.material_id, engine);
      const taskId = resp.task_id;
      // 轮询解析任务
      const poll = async () => {
        try {
          const status = await materialUnitApi.parseTaskStatus(unit.id, taskId);
          setParseProgress(status);
          if (['completed', 'failed'].includes(status.status)) {
            setError(status.status === 'failed' ? (status.materials?.find((m) => m.id === file.material_id)?.message || '重新识别失败') : '');
            // 完成/失败: 尽力刷新一次, 失败也不重试(避免无限循环)
            if (status.status === 'completed') {
              try {
                const updated = await materialUnitApi.get(unit.id);
                const freshFile = updated?.files?.find((f) => f.material_id === file.material_id);
                if (freshFile) setPreviewFile(freshFile);
                const textResp = await materialUnitApi.fileText(unit.id, file.material_id);
                setRawText(textResp?.text || freshFile?.summary || '');
                setRawPages(textResp?.pages || null);
                setNotice(`已用 ${engine} 重新识别，文本已更新。`);
                await refresh();
              } catch { /* 刷新失败不重试 */ }
            }
            setRawLoading(false);
            return;
          }
          window.setTimeout(poll, 1200);
        } catch (_e) {
          window.setTimeout(poll, 1500);
        }
      };
      void poll();
    } catch (reason) {
      setError(getErrorMessage(reason)); setRawLoading(false);
    }
  };

  const runMatch = async (sessionId: string) => {
    if (!unit || !sessionId) return;
    setSelectedSession(sessionId); setMatching(true); setError(''); setSelectedRequirements([]);
    try {
      const result = await materialUnitApi.syllabusMatches(unit.id, [sessionId]);
      setAlignment(result);
      setSelectedRequirements(result.matches.filter((item) => item.recommended).map((item) => item.id));
    } catch (reason) { setError(getErrorMessage(reason)); setAlignment(null); }
    finally { setMatching(false); }
  };

  const toggle = (values: string[], value: string, setter: (next: string[]) => void) => {
    setter(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  };

  // 挂载图谱节点到当前大纲的知识点节点
  const mountGraphToNode = async (graphId: string, targetNodeId: string) => {
    if (!unit || !outline) return;
    await materialUnitApi.graphNodeInsertOutline(unit.id, graphId, { outline_id: outline.id, node_id: targetNodeId });
    setNotice('教材研读补充已挂载到知识点');
    await refresh();
  };

  // 一键导入全部: 串行(顺序)提交, 与后端 asyncio.Lock 配合避免并发读-改-写丢失更新
  const importNodes = async (ids: string[], nodeId: string) => {
    setMutating(true);
    try {
      let failed = 0;
      for (const id of ids) {
        try { await mountGraphToNode(id, nodeId); }
        catch { failed += 1; }
      }
      setNotice(failed ? `${ids.length - failed} 个导入成功，${failed} 个失败（请重试）` : `已导入 ${ids.length} 个图谱节点`);
    } finally { setMutating(false); setInsertPicker(null); }
  };

  const openInsertPicker = (nodeTitle: string, nodeId: string) => {
    const nodes = graphNodesFor(nodeTitle);
    if (!nodes.length) return;
    // 收集该章节图谱节点及其子节点树(树形展示)
    const ids = new Set(nodes.map((n) => n.id));
    let changed = true;
    while (changed) {
      changed = false;
      for (const g of unitGraphNodes) {
        if (g.parent_id && ids.has(g.parent_id) && !ids.has(g.id)) { ids.add(g.id); changed = true; }
      }
    }
    const all = unitGraphNodes.filter((g) => ids.has(g.id));
    setInsertPicker({ title: nodeTitle, nodeId, nodes: all });
    setGraphSelectedId(all[0]?.id || '');
    setGraphImportSet(new Set(all.map((g) => g.id)));
  };

  // ---- 三列可拖动: 分隔条 pointer 事件 ----
  const startSplitDrag = (which: '0' | '1') => (e: React.PointerEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const wrap = document.querySelector('.material-unit-layout');
    const side = wrap?.querySelector('.unit-sidebar');
    const outline = wrap?.querySelector('.outline-panel');
    // 0=拖 side|main 边界(改 side 宽); 1=拖 main|outline 边界(改 outline 宽)
    const startW = which === '0'
      ? (side?.getBoundingClientRect().width ?? 250)
      : (outline?.getBoundingClientRect().width ?? 430);
    dragSplit.current = { which, startX, startW };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onSplitMove = (e: React.PointerEvent) => {
    const d = dragSplit.current;
    if (!d) return;
    const delta = e.clientX - d.startX;
    if (d.which === '0') {
      // 拖 side|main 边界: 分隔条跟随鼠标 → 向右拖→右侧(main)变窄, side(左)变宽
      const w = Math.min(450, Math.max(200, d.startW + delta));
      setColW((cur) => ({ ...cur, side: w }));
    } else {
      // 拖 main|outline 边界: 向右拖→右侧(outline)变窄
      const w = Math.min(640, Math.max(320, d.startW - delta));
      setColW((cur) => ({ ...cur, outline: w }));
    }
  };
  const endSplitDrag = () => { dragSplit.current = null; };
  // 三列用 CSS 变量驱动列宽(flex-basis), 拖动时实时更新
  const muLayoutStyle: React.CSSProperties | undefined = (colW.side || colW.outline)
    ? ({ '--muw-side': `${colW.side ?? 260}px`, '--muw-outline': `${colW.outline ?? 420}px` } as React.CSSProperties)
    : undefined;

  // ---- 教学补充: 提示词 → dsh 生成候选 → 预览 → 同意/编辑后落库 ----
  const openTeacherNote = (nodeId: string, nodeTitle: string) => {
    setTeacherNoteDlg({ nodeId, nodeTitle });
    setTnInstruction('');
    setTnGenerated('');
    setTnEditing(false); setTnBusy(false);
  };
  const generateTeacherNote = async () => {
    if (!unit || !outline || !teacherNoteDlg || !tnInstruction.trim()) return;
    setTnBusy(true); setError('');
    try {
      const res = await materialUnitApi.generateTeacherNote(unit.id, outline.id, teacherNoteDlg.nodeId, { version: outline.version, instruction: tnInstruction.trim() });
      setTnGenerated(res.content); setTnEditing(false);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setTnBusy(false); }
  };
  const saveTeacherNote = async () => {
    if (!unit || !outline || !teacherNoteDlg || !tnGenerated.trim()) return;
    setTnBusy(true); setError('');
    try {
      await materialUnitApi.saveTeacherNote(unit.id, outline.id, teacherNoteDlg.nodeId, { version: outline.version, content: tnGenerated });
      setTeacherNoteDlg(null);
      await refresh();  // 刷新大纲, 就地更新的 teacher_note 反映到界面
      setNotice('教学补充已保存。');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setTnBusy(false); }
  };

  const createOutline = async () => {    if (!unit || !selectedSession) return;
    setMutating(true); setError('');
    try {
      const created = await materialUnitApi.createKnowledgeOutline(unit.id, {
        teaching_item_ids: [selectedSession], syllabus_item_ids: selectedRequirements,
        outline_node_ids: selectedTextbook, status: 'draft',
      });
      setOutlines((current) => [...current, created]); selectOutline(created);
      setNotice('知识大纲已生成并保存为第 1 版。');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMutating(false); }
  };

  const saveOutlineVersion = async (status: 'draft' | 'confirmed' = outline?.status || 'draft') => {
    if (!unit || !outline || !draftTitle.trim() || !draftNodes.length) return;
    setMutating(true); setError('');
    try {
      const saved = await materialUnitApi.updateKnowledgeOutline(unit.id, outline.id, {
        base_version: outline.version, title: draftTitle.trim(), status, nodes: draftNodes,
        change_summary: status === 'confirmed' ? '教师确认知识范围' : '教师编辑知识大纲',
      });
      setOutlines((current) => [...current, saved]); selectOutline(saved);
      setNotice(`已保存第 ${saved.version} 版知识大纲。`);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMutating(false); }
  };

  const refineOutline = async () => {
    if (!unit || !outline || !refineMaterials.length || refineInstruction.trim().length < 2) return;
    setMutating(true); setError('');
    try {
      const task = await materialUnitApi.createRefineTask(unit.id, outline.id, {
        material_ids: refineMaterials, teacher_instruction: refineInstruction.trim(), base_version: outline.version, use_model: true,
      });
      setRefineTask(task);
      setNotice('细化任务已在后台启动，可以切换页面，返回后会继续显示进度。');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMutating(false); }
  };

  // AI 优化: 直接按提示词优化当前大纲版本 (不依赖资料, free_instruction_mode)
  const optimizeCurrentOutline = async () => {
    if (!unit || !outline || aiOptimizeInstruction.trim().length < 2) return;
    setOptimizing(true); setError('');
    try {
      const result = await materialUnitApi.refineKnowledgeOutline(unit.id, outline.id, {
        material_ids: [], teacher_instruction: aiOptimizeInstruction.trim(), base_version: outline.version, use_model: true,
      });
      setOutlines((items) => [result, ...items.filter((i) => !(i.id === result.id && i.version === result.version))]);
      selectOutline(result);
      setAiOptimizeOpen(false); setAiOptimizeInstruction('');
      setNotice(`已按提示词生成优化版本（第 ${result.version} 版），原版本保留可回退。`);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setOptimizing(false); }
  };

  const importToDesign = async () => {
    if (!unit || !dialog || dialog.mode !== 'import-design') return;
    const [outlineId, versionText] = dialog.outlineKey.split(':');
    const selectedOutline = outlines.find((item) => item.id === outlineId && item.version === Number(versionText));
    if (!selectedOutline) return;
    setMutating(true); setError(''); setImportParsing(null);
    try {
      // 步骤1: 解析预检 —— 凡未完整提取的材料先触发后台解析，保证进入课程设计的都是解析版(不二次解析)
      const precheck = await materialUnitApi.importPrecheck(unit.id, dialog.materialIds);
      if (!precheck.all_parsed && precheck.needs_parse.length) {
        const taskId = (await materialUnitApi.parseTask(unit.id, precheck.needs_parse.map((item) => item.material_id))).task_id;
        const total = precheck.needs_parse.length;
        const initial = precheck.needs_parse.map((item) => ({ id: item.material_id, name: item.name, status: item.parse_status === 'parsed' ? 'cached' : 'pending', progress: item.parse_status === 'parsed' ? 100 : 0, message: '' }));
        const done = await runParseWithProgress(taskId, unit.id, total, initial);
        setImportParsing(done);
        // 重新 precheck，确认全部已解析后落库
        const recheck = await materialUnitApi.importPrecheck(unit.id, dialog.materialIds);
        if (!recheck.all_parsed) throw new Error('仍存在未能解析的材料，请检查后重试。');
      }
      // 步骤2: 全部已解析 → 真正创建课程设计
      const design = await courseDesignApi.create({
        archive_id: unit.archive_id, material_ids: dialog.materialIds, primary_material_id: dialog.primaryMaterialId,
        material_unit_id: unit.id, knowledge_outline_id: selectedOutline.id, knowledge_outline_version: selectedOutline.version,
      });
      setDialog(null); setImportParsing(null);
      setNotice(`知识大纲 v${selectedOutline.version} 与 ${dialog.materialIds.length} 份已解析资料导入课程设计。`);
      await onCourseDesignCreated(design);
    } catch (reason) { setError(getErrorMessage(reason)); setImportParsing(null); }
    finally { setMutating(false); }
  };

  // 轮询解析任务直至全部完成/失败，返回最终进程状态供展示；期间并行进度条实时更新。
  const runParseWithProgress = async (
    taskId: string, unitId: string, total: number,
    initial: Array<{ id: string; name: string; status: string; progress: number; message: string }>,
  ): Promise<{ taskId: string; total: number; materials: Array<{ id: string; name: string; status: string; progress: number; message: string }> }> => {
    let last: typeof initial = initial;
    await new Promise<void>((resolve, reject) => {
      const poll = async () => {
        try {
          const task = await materialUnitApi.parseTaskStatus(unitId, taskId);
          last = (task.materials || []).map((m) => ({ id: m.id, name: m.name, status: m.status, progress: m.progress, message: m.message }));
          setImportParsing({ taskId, total, materials: last });
          const terminal = (task.materials || []).every((m) => ['parsed', 'cached', 'failed'].includes(m.status)) || task.status === 'completed';
          if (terminal) {
            if (importPollRef.current) clearInterval(importPollRef.current); importPollRef.current = null;
            if (task.status === 'completed') resolve(); else reject(new Error('部分材料解析失败或超时，请查看详情。'));
          }
        } catch (reason) { if (importPollRef.current) clearInterval(importPollRef.current); importPollRef.current = null; reject(reason); }
      };
      importPollRef.current = setInterval(poll, 1500);
      void poll();
    });
    return { taskId, total, materials: last };
  };

  const submitDialog = async () => {
    if (!dialog) return;
    setMutating(true); setError('');
    try {
      if (dialog.mode === 'rename') await materialUnitApi.rename(dialog.unit.id, dialog.title.trim());
      if (dialog.mode === 'delete') await materialUnitApi.remove(dialog.unit.id);
      if (dialog.mode === 'merge') await materialUnitApi.merge(dialog.target.id, dialog.sourceIds, dialog.title.trim());
      if (dialog.mode === 'link-files') await materialUnitApi.referenceMaterials(dialog.target.id, dialog.sourceUnitId, dialog.materialIds);
      if (dialog.mode === 'delete-outline') await materialUnitApi.deleteKnowledgeOutline(unit!.id, dialog.outline.id, dialog.outline.version, dialog.allHistory);
      if (dialog.mode === 'import-design') { await importToDesign(); return; }
      setDialog(null); await refresh();
      setNotice(dialog.mode === 'merge' ? '资料已整合为一个单元。' : dialog.mode === 'link-files' ? '已关联所选文件，来源单元保持不变。' : dialog.mode === 'delete-outline' ? '知识大纲历史已更新。' : '操作已完成。');
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMutating(false); }
  };

  const removeFileReference = async (referenceId: string) => {
    if (!unit) return;
    setMutating(true);
    try { const saved = await materialUnitApi.removeMaterialReference(unit.id, referenceId); setUnit(saved); setNotice('已解除文件关联，来源文件未删除。'); }
    catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMutating(false); }
  };

  const availableFiles = useMemo(() => unit ? [
    ...unit.files.map((file) => ({ ...file, sourceLabel: unit.title })),
    ...unit.linked_units.flatMap((linked) => linked.files.map((file) => ({ ...file, sourceLabel: linked.title }))),
    ...unit.material_references.map((reference) => ({ ...reference.file, sourceLabel: reference.source_unit_title })),
  ].filter((file, index, values) => values.findIndex((item) => item.material_id === file.material_id) === index) : [], [unit]);
  const designImportFiles = useMemo(
    () => availableFiles.filter((file) => !file.archive_id || file.archive_id === unit?.archive_id),
    [availableFiles, unit?.archive_id],
  );
  // 导入默认选中"知识范围"里已勾选的教材文件（而不是默认全选），便于聚焦本次课材料
  const defaultImportMaterialIds = useMemo(() => {
    const selectedNodeMaterial = new Set(
      (scope?.textbook_outline || [])
        .filter((node) => selectedTextbook.includes(node.id))
        .map((node) => node.source_material_id)
        .filter((id) => designImportFiles.some((file) => file.material_id === id)),
    );
    const ids = [...selectedNodeMaterial];
    if (ids.length === 0) {
      const firstTextbook = designImportFiles.find((file) => file.category === 'textbook');
      if (firstTextbook) ids.push(firstTextbook.material_id);
    }
    return ids;
  }, [scope?.textbook_outline, selectedTextbook, designImportFiles]);
  const getDefaultImportPrimary = (ids: string[]) =>
    ids.length ? (designImportFiles.find((file) => ids.includes(file.material_id) && file.category === 'textbook')?.material_id || ids[0]) : '';

  const latest = latestOutlines(outlines);
  const sessionItem = scope?.teaching_items.find((item) => item.id === selectedSession);

  if (loading && !units.length) return <div className="material-unit-loading"><Loader2 className="spin" size={22} /><strong>正在读取资料单元…</strong></div>;
  return <div className="material-unit-workspace">
    <header className="material-unit-toolbar">
      <div><span>资料单元</span><h2>建立本次课知识范围</h2><p>先选讲次，系统匹配相关大纲要求，再用教材章节形成可追溯的知识大纲。</p></div>
      <div><button type="button" onClick={() => void refresh()} disabled={loading}><RefreshCw className={loading ? 'spin' : ''} size={16} />刷新</button><button type="button" onClick={onGoLibrary}><ArrowLeft size={16} />课程资料库</button></div>
    </header>
    {(error || notice) && <div className={`material-unit-message ${error ? 'is-error' : ''}`}><AlertCircle size={16} /><span>{error || notice}</span><button type="button" onClick={() => { setError(''); setNotice(''); }} aria-label="关闭提示"><X size={15} /></button></div>}
    {!units.length ? <main className="material-unit-empty"><Database size={30} /><h3>还没有资料单元</h3><p>请先到课程资料库选择进度表、大纲和教材。</p><button type="button" onClick={onGoLibrary}>前往课程资料库</button></main> : <div className="material-unit-layout" style={muLayoutStyle}>
      <div className="mu-split" data-split="0" onPointerDown={startSplitDrag('0')} onPointerMove={onSplitMove} onPointerUp={endSplitDrag} /><aside className="unit-sidebar">
        <header><strong>单元列表</strong><span>{units.length}</span></header>
        <div className="unit-list">{units.map((item) => <div key={item.id} className={`unit-list-item ${unit?.id === item.id ? 'active' : ''}`}><button type="button" onClick={() => void openUnit(item.id)}><Database size={17} /><span><strong>{item.title}</strong><small>{item.material_count} 份资料 · {item.linked_unit_count} 个关联</small><time>{formatDate(item.updated_at)}</time></span></button><div><button type="button" title="重命名" onClick={() => setDialog({ mode: 'rename', unit: item, title: item.title })}><Edit3 size={14} /></button><button type="button" title="删除" onClick={() => setDialog({ mode: 'delete', unit: item })}><Trash2 size={14} /></button></div></div>)}</div>
        <footer><button type="button" disabled={!unit || units.length < 2} onClick={() => unit && setDialog({ mode: 'link-files', target: unit, sourceUnitId: '', materialIds: [] })}><Link2 size={15} />关联其他单元资料</button><button type="button" disabled={!unit || units.length < 2} onClick={() => unit && setDialog({ mode: 'merge', target: unit, sourceIds: [], title: unit.title })}><GitMerge size={15} />整合为一个单元</button></footer>
        {unit && <section className="unit-sources"><header><strong>当前资料</strong><span>{availableFiles.length}</span></header>{availableFiles.map((file) => <button type="button" key={file.material_id} onClick={() => void openFilePreview(file)}><Files size={15} /><span><strong>{file.name}</strong><small>{categoryLabels[file.category] || file.category} · {file.parse_status === 'parsed' ? `已提取 ${file.character_count} 字` : file.parse_status === 'parse_failed' ? '提取失败' : file.parse_status === 'unsupported' ? '格式不支持' : '未提取'}<i className={`parse-dot ${file.parse_status}`} /></small></span></button>)}{unit.material_references.map((reference) => <div className="file-reference" key={reference.id}><Link2 size={14} /><span><strong>{reference.file.name}</strong><small>关联自 {reference.source_unit_title}</small></span><button type="button" onClick={() => void removeFileReference(reference.id)} title="解除关联"><Unlink size={14} /></button></div>)}</section>}
      </aside>

      <main className="scope-workbench">
        {detailLoading ? <div className="material-unit-loading"><Loader2 className="spin" size={22} /><strong>正在整理讲次、大纲和教材…</strong></div> : <>
          <section className="planning-step is-open"><header><span>1</span><div><strong>选择本次课</strong><small>从进度表中选择一条课程安排</small></div><em>{selectedSession ? '已选择' : '待选择'}</em></header><div className="session-options module-scroll">{(() => { const all = scope?.teaching_items || []; const scheduleIds = [...new Set(all.map((i) => i.source_material_id))]; const filtered = scheduleFilter === 'all' ? all : all.filter((i) => i.source_material_id === scheduleFilter); if (!all.length) return <p className="step-empty">尚未识别到进度表，请关联或导入进度表文件。</p>; return <><div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '0 0 8px' }}><small style={{ color: '#6b7e93', fontSize: 12 }}>进度表来源</small><select value={scheduleFilter} onChange={(event) => { setScheduleFilter(event.target.value); setSelectedSession(''); }} style={{ fontSize: 12, padding: '3px 8px', border: '1px solid #cbd8e5', borderRadius: 5, background: '#fff' }}><option value="all">全部进度表（{scheduleIds.length} 份）</option>{scheduleIds.map((mid) => <option key={mid} value={mid}>{all.find((i) => i.source_material_id === mid)?.source_name || mid.slice(0, 8)}</option>)}</select><small style={{ color: '#6b7e93', fontSize: 11 }}>切换来源后需重新选择讲次（大纲匹配随之更新）</small></div>{filtered.map((item) => <button type="button" key={item.id} className={selectedSession === item.id ? 'selected' : ''} onClick={() => void runMatch(item.id)}><span className="radio-mark">{selectedSession === item.id && <Check size={13} />}</span><span><strong>{item.title}</strong><small>{item.content}</small><em>来源：{item.source_name}</em></span></button>)}</>; })()}</div></section>

          <section className="planning-step is-open"><header><span>2</span><div><strong>核对相关大纲要求</strong><small>系统只展示与当前讲次相关的目标、重点和难点</small></div><em>{matching ? '匹配中' : alignment ? `${alignment.matches.length} 条` : '等待讲次'}</em></header>{selectedSession && <div className="alignment-content module-scroll">{(() => { if (matching) return <div className="inline-loading"><Loader2 className="spin" size={18} />正在根据“{sessionItem?.title}”分析教学大纲…</div>; if (!alignment?.matches.length) return <p className="step-empty">没有找到可靠匹配。仍可继续选择教材，生成结果会标记“大纲依据缺失”。</p>; const sourceIds = [...new Set(alignment.matches.map((i) => i.evidence?.material_id).filter((v): v is string => Boolean(v)))]; const visible = syllabusFilter === 'all' ? alignment.matches : alignment.matches.filter((i) => !i.evidence?.material_id || i.evidence?.material_id === syllabusFilter); const nameOfS = (mid: string) => unit?.files?.find((f) => f.material_id === mid)?.name || mid.slice(0, 16); return (<>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '0 0 8px' }}>
        <small style={{ color: '#6b7e93', fontSize: 12 }}>大纲来源</small>
        <select value={syllabusFilter} onChange={(event) => setSyllabusFilter(event.target.value)} style={{ fontSize: 12, padding: '3px 8px', border: '1px solid #cbd8e5', borderRadius: 5, background: '#fff' }}>
          <option value="all">全部大纲（{sourceIds.length} 份）</option>
          {sourceIds.map((mid) => <option key={mid} value={mid}>{nameOfS(mid)}</option>)}
        </select>
        <small style={{ color: '#6b7e93', fontSize: 11 }}>导入新大纲后，重新选择讲次即可重新匹配</small>
      </div>
      {(['objective', 'knowledge', 'key_point', 'difficult_point', 'practice', 'assessment'] as SyllabusRequirementType[]).map((category) => { const items = visible.filter((item) => item.category === category); return items.length ? <div className="requirement-group" key={category}><h4>{requirementLabels[category]}<span>{items.length}</span></h4>{items.map((item) => <label key={item.id} className={selectedRequirements.includes(item.id) ? 'selected' : ''}><input type="checkbox" checked={selectedRequirements.includes(item.id)} onChange={() => toggle(selectedRequirements, item.id, setSelectedRequirements)} /><span><strong>{item.title}</strong><small>{item.content}</small><em>{Math.round(item.score * 100)}% · {item.reason}</em></span></label>)}</div> : null; })}
      <details className="matching-meta"><summary>查看匹配说明</summary><p>{alignment?.model_used ? '已使用智能体语义判断并结合章节、关键词证据。' : '当前使用章节、关键词和文本相似度匹配。'}候选大纲共 {alignment?.total_candidates || 0} 条。</p></details>
    </>); })()}</div>}</section>

          <section className="planning-step is-open"><header><span>3</span><div><strong>确定教材知识范围</strong><small>按一级、二级、三级标题选择本次课需要覆盖的知识点</small></div><em>{selectedTextbook.length} 项</em></header><div className="textbook-tree module-scroll">{(() => { const all = scope?.textbook_outline || []; const materialIds = [...new Set(all.map((i) => i.source_material_id))]; const nameOf = (mid: string) => unit?.files?.find((f) => f.material_id === mid)?.name || all.find((i) => i.source_material_id === mid)?.source_name || mid.slice(0, 8); const sourceOptions = materialIds.map((mid) => ({ mid, name: nameOf(mid) })); const filtered = textbookFilter === 'all' ? all : all.filter((i) => i.source_material_id === textbookFilter); if (!all.length) return <p className="step-empty">尚未识别到教材目录，请关联或导入教材文件（需为"教材"类且已识别）。</p>; return <><div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '0 0 8px' }}><small style={{ color: '#6b7e93', fontSize: 12 }}>教材来源</small><select value={textbookFilter} onChange={(event) => setTextbookFilter(event.target.value)} style={{ fontSize: 12, padding: '3px 8px', border: '1px solid #cbd8e5', borderRadius: 5, background: '#fff', maxWidth: 340 }}><option value="all">全部教材（{sourceOptions.length} 本）</option>{sourceOptions.map((o) => <option key={o.mid} value={o.mid}>{o.name}</option>)}</select>{!selectedSession && <small style={{ color: '#b45309', fontSize: 11 }}>提示：先在步骤1选择讲次，可按讲次匹配大纲要求（教材目录可先浏览）</small>}</div>{filtered.map((item) => { const graphFor = unitGraphNodes.filter((g) => (g.quote && (item.title && g.quote.includes(item.title))) || g.material_id === item.source_material_id); return <label key={item.id} className={`level-${item.level} ${selectedTextbook.includes(item.id) ? 'selected' : ''}`}><input type="checkbox" checked={selectedTextbook.includes(item.id)} onChange={() => toggle(selectedTextbook, item.id, setSelectedTextbook)} /><span style={{ minWidth: 0 }}><strong>{item.title}</strong><small>{item.preview || `来源：${nameOf(item.source_material_id)}`}</small>{graphFor.length > 0 && <small style={{ color: '#1857b7', fontWeight: 700 }}>📖 图谱节点 {graphFor.length} 个 — 选中本节点后可插入</small>}</span></label>; })}</>; })()}</div></section>

          <footer className="scope-actions"><div><strong>{sessionItem?.title || '尚未选择讲次'}</strong><span>已选 {selectedRequirements.length} 条大纲要求、{selectedTextbook.length} 个教材标题</span></div><button type="button" disabled={mutating || !selectedSession || (!selectedRequirements.length && !selectedTextbook.length)} onClick={() => void createOutline()}>{mutating ? <Loader2 className="spin" size={16} /> : <BookOpen size={16} />}生成知识大纲</button></footer>
        </>}
      </main>

      <div className="mu-split" data-split="1" onPointerDown={startSplitDrag('1')} onPointerMove={onSplitMove} onPointerUp={endSplitDrag} /><aside className="outline-panel">
        <header><div><span>本次课成果</span><strong>知识大纲</strong><small>只定义要讲的知识点，不编排教学活动和讲解顺序</small></div>{outline && <select value={`${outline.id}:${outline.version}`} onChange={(event) => { const [id, version] = event.target.value.split(':'); selectOutline(outlines.find((item) => item.id === id && item.version === Number(version)) || null); }}>{outlines.slice().sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map((item) => <option key={`${item.id}:${item.version}`} value={`${item.id}:${item.version}`}>v{item.version} · {item.title}</option>)}</select>}<button type="button" className="outline-history-btn" title="版本历史" onClick={() => setOutlineHistoryOpen(true)}><History size={13} /></button>{outline && <button type="button" className="outline-import-btn" onClick={() => { const ids = defaultImportMaterialIds; setDialog({ mode: 'import-design', outlineKey: `${outline.id}:${outline.version}`, materialIds: ids, primaryMaterialId: getDefaultImportPrimary(ids) }); }}><Send size={13} />导入课程设计</button>}</header>
        {!outline ? <div className="outline-empty"><BookOpen size={28} /><strong>尚未生成知识大纲</strong><span>完成左侧范围规划后，结果会固定显示在这里。</span>{latest.length > 0 && <button type="button" onClick={() => selectOutline(latest[0])}>打开最近大纲</button>}</div> : <>
          <div className="outline-status"><span className={outline.status === 'confirmed' ? 'confirmed' : ''}>{outline.status === 'confirmed' ? '已确认' : '草稿'}</span><strong>第 {outline.version} 版</strong><small>{outline.change_summary}</small></div>
          <div className="outline-tools"><button type="button" onClick={() => setOutlineEditing((value) => !value)}><Edit3 size={15} />{outlineEditing ? '结束编辑' : '编辑大纲'}</button><button type="button" onClick={() => { setAiOptimizeOpen((v) => !v); setRefineOpen(false); }}><Sparkles size={15} />AI 优化</button><button type="button" onClick={() => setRefineOpen((value) => !value)}><FilePlus2 size={15} />基于资料细化</button><button type="button" className="danger" onClick={() => setDialog({ mode: 'delete-outline', outline, allHistory: false })}><Trash2 size={15} />删除版本</button></div>
          {aiOptimizeOpen && <section className="refine-panel"><header><strong>AI 优化当前大纲（按提示词）</strong><button type="button" onClick={() => setAiOptimizeOpen(false)} aria-label="关闭优化面板"><X size={15} /></button></header><p>直接对右侧当前版本的大纲进行优化：可重排结构、合并拆分知识点、调整重点难点标注、补充或删减内容。结果保存为新版本，原版本保留。</p><textarea value={aiOptimizeInstruction} onChange={(event) => setAiOptimizeInstruction(event.target.value)} placeholder="例如：把 1.2 和 1.3 合并为'环境搭建'一个知识点；为每个二级知识点标注重点；去掉与本章无关的内容；按'概念→操作→练习'重新排序。" /><button type="button" disabled={optimizing || aiOptimizeInstruction.trim().length < 2 || Boolean(refineTask && !['completed', 'failed'].includes(refineTask.status))} onClick={() => void optimizeCurrentOutline()}>{optimizing ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />}生成优化版本</button></section>}
          {outlineEditing ? <div className="outline-editor"><label>大纲名称<input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} /></label><div className="node-editor-list">{draftNodes.map((node, index) => <div key={node.id} className="node-editor-row"><select value={node.level} onChange={(event) => setDraftNodes((current) => current.map((item) => item.id === node.id ? { ...item, level: Number(event.target.value) } : item))}><option value={1}>一级</option><option value={2}>二级</option><option value={3}>三级</option></select><input value={node.title} onChange={(event) => setDraftNodes((current) => current.map((item) => item.id === node.id ? { ...item, title: event.target.value } : item))} /><div><label><input type="checkbox" checked={node.is_key_point} onChange={(event) => setDraftNodes((current) => current.map((item) => item.id === node.id ? { ...item, is_key_point: event.target.checked } : item))} />重点</label><label><input type="checkbox" checked={node.is_difficult_point} onChange={(event) => setDraftNodes((current) => current.map((item) => item.id === node.id ? { ...item, is_difficult_point: event.target.checked } : item))} />难点</label></div><span><button type="button" disabled={index === 0} onClick={() => setDraftNodes((current) => { const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next; })}><ArrowUp size={14} /></button><button type="button" disabled={index === draftNodes.length - 1} onClick={() => setDraftNodes((current) => { const next = [...current]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; return next; })}><ArrowDown size={14} /></button><button type="button" onClick={() => setDraftNodes((current) => current.filter((item) => item.id !== node.id))}><Trash2 size={14} /></button></span><textarea className="node-teacher-editor" value={node.teacher_note || ''} placeholder="教学补充（可编辑/删减，空则删除）" onChange={(event) => setDraftNodes((current) => current.map((item) => item.id === node.id ? { ...item, teacher_note: event.target.value } : item))} rows={3} /></div>)}</div><button type="button" className="add-node" onClick={() => setDraftNodes((current) => [...current, { id: crypto.randomUUID(), parent_id: null, level: 1, title: '新增知识点', description: '', is_key_point: false, is_difficult_point: false, teacher_note: '教师新增', evidence: [{ source_type: 'teacher', locator: '', quote: '教师新增知识点', label: '教师补充' }] }])}><Plus size={15} />新增知识点</button></div> : <div className="outline-tree"><h3>{outline.title}</h3>{draftNodes.map((node) => { const gFor = graphNodesFor(node.title); return <article key={node.id} className={`level-${node.level}`}><div><strong>{node.title}</strong><span>{node.is_key_point && <em>重点</em>}{node.is_difficult_point && <em className="difficult">难点</em>}{gFor.length > 0 && <button type="button" className="graph-insert-btn" title={`教材研读：${gFor.map((g) => g.title).join('、')}`} onClick={() => openInsertPicker(node.title, node.id)}>📖 教材研读{gFor.length > 1 ? ` ${gFor.length}` : ''}</button>}</span></div>{node.description ? <details className="node-desc" open={node.level === 1}><summary>查看说明</summary><p>{node.description}</p></details> : null}<details className="node-evidence" open={false}><summary>{node.evidence.length} 条来源依据</summary>{node.evidence.map((evidence, index) => <blockquote key={evidence.id || `${node.id}:${index}`}><b>{evidence.label || evidence.source_type}</b><span>{evidence.quote}</span><small>{evidence.locator}</small></blockquote>)}</details>{node.teacher_note ? <details className="node-teacher-note" open={false}><summary>📖 教学补充<button type="button" className="teacher-note-edit-btn" title="编辑教学补充" onClick={(e) => { e.preventDefault(); e.stopPropagation(); openTeacherNote(node.id, node.title); }}><Edit3 size={11} />编辑</button></summary><div style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.7, color: '#40546d', background: '#f2f8ff', border: '1px solid #cfe0f5', borderRadius: 5, padding: 7, marginTop: 5 }}>{(node.teacher_note || '').replace(/^```(?:json|md|markdown)?\s*/m, '').replace(/\s*```\s*$/m, '').slice(0, 600)}</div><div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}><div className="graph-unlink-list">{(node.evidence || []).filter((e) => String(e.locator || '').startsWith('graph:')).map((ev, ei) => { const gid = String(ev.locator).split('graph:')[1]; const gTitle = ev.quote || '教材研读补充'; return <button type="button" key={ei} className="graph-unlink-btn" title={`取消导入 ${gTitle}`} onClick={() => { if (window.confirm(`取消导入「${gTitle}」这份教材研读补充？`)) void materialUnitApi.graphNodeUnlinkOutline(unit!.id, gid, { outline_id: outline!.id, node_id: node.id }).then(() => void refresh()).catch((reason) => setError(getErrorMessage(reason))); }}><Unlink size={12} />取消导入：{gTitle.replace('教材研读补充：', '').slice(0, 14)}</button>; })}<button type="button" className="graph-unlink-btn" title="用提示词重新生成教学补充" onClick={() => { openTeacherNote(node.id, node.title); }}><Sparkles size={12} />AI 重新生成</button></div></div></details> : <button type="button" className="teacher-note-add-btn" onClick={() => openTeacherNote(node.id, node.title)}><Sparkles size={12} />教学补充</button>}</article>})}</div>}
          {refineTask && refineTask.outline_id === outline.id && <section className={`refine-task-status is-${refineTask.status}`}><header><span>{refineTask.status === 'completed' ? <CheckCircle2 size={16} /> : refineTask.status === 'failed' ? <AlertCircle size={16} /> : <Loader2 className="spin" size={16} />}<strong>{refineTask.stage_label}</strong></span><time>{refineTask.elapsed_seconds} 秒</time></header><div className="refine-progress"><span style={{ width: `${refineTask.progress}%` }} /></div><footer><span>{refineTask.progress}%</span><small>{refineTask.status === 'completed' ? `结果：第 ${refineTask.result_version} 版` : refineTask.status === 'failed' ? refineTask.error : '任务由后端持续执行，切换页面不会中断'}</small></footer></section>}
          {refineOpen && <section className="refine-panel"><header><strong>在已选范围内细化</strong><button type="button" onClick={() => setRefineOpen(false)} aria-label="关闭细化面板"><X size={15} /></button></header><p>当前大纲是固定边界。所选资料只用于补充现有知识点的下级内容和原文依据，不会加入未选择的章节。</p><div>{availableFiles.map((file) => <label key={file.material_id}><input type="checkbox" checked={refineMaterials.includes(file.material_id)} onChange={() => toggle(refineMaterials, file.material_id, setRefineMaterials)} /><span><strong>{file.name}</strong><small>{file.sourceLabel}</small></span></label>)}</div><textarea value={refineInstruction} onChange={(event) => setRefineInstruction(event.target.value)} placeholder="例如：细化当前知识点的概念、边界条件与公式含义，不扩展到其他章节。" /><button type="button" disabled={mutating || Boolean(refineTask && !['completed', 'failed'].includes(refineTask.status)) || !refineMaterials.length || refineInstruction.trim().length < 2} onClick={() => void refineOutline()}>{mutating ? <Loader2 className="spin" size={15} /> : <FileSearch size={15} />}生成范围内细化版本</button></section>}
          <footer className="outline-actions"><button type="button" disabled={mutating || !draftNodes.length} onClick={() => void saveOutlineVersion('draft')}><Save size={15} />保存新版本</button><button type="button" disabled={mutating || !draftNodes.length} onClick={() => void saveOutlineVersion('confirmed')}><CheckCircle2 size={15} />确认知识范围</button></footer>
        </>}
      </aside>
    </div>}
    {dialog && <UnitDialog dialog={dialog} units={units} files={designImportFiles} outlines={outlines} mutating={mutating} onChange={setDialog} onClose={() => setDialog(null)} onSubmit={() => void submitDialog()} />}
    {importParsing && <div className="unit-dialog-backdrop" role="presentation"><section className="unit-dialog import-parse-progress" role="dialog" aria-modal="true"><header><div><Loader2 className="spin" size={18} /><span><strong>正在补齐材料解析</strong><small>进入课程设计前，确保所选材料均为可复用的解析正文，避免后续重复解析</small></span></div></header><div className="import-parse-body">{importParsing.materials.length === 0 ? <div className="inline-loading"><Loader2 className="spin" size={18} />正在检查解析状态…</div> : importParsing.materials.map((m) => <div className="import-parse-row" key={m.id}><span className="import-parse-name">{m.name}</span><div className="import-parse-track"><span className={`import-parse-fill ${m.status === 'failed' ? 'is-failed' : m.status === 'parsed' || m.status === 'cached' ? 'is-done' : ''}`} style={{ width: `${m.progress}%` }} /></div><em>{m.status === 'failed' ? '失败' : m.status === 'parsed' || m.status === 'cached' ? '完成' : `${m.progress}%`}</em></div>)}</div><footer className="dialog-footer"><span className="import-parse-hint">完成后将自动创建课程设计并保存解析结果</span></footer></section></div>}
    {previewFile && <FilePreview file={previewFile} onClose={() => setPreviewFile(null)} rawText={rawText} rawPages={rawPages} rawLoading={rawLoading} parseProgress={parseProgress} onReparse={(engine) => void reparseFile(previewFile, engine)} unitId={unit?.id || ''} />}
    {teacherNoteDlg && outline && <div className="unit-dialog-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setTeacherNoteDlg(null)}><section className="unit-dialog teacher-note-dialog" role="dialog" aria-modal="true"><header><div><Sparkles size={18} /><span><strong>教学补充 · {teacherNoteDlg.nodeTitle}</strong><small>输入要求，dsh 根据当前大纲为该知识点生成教学补充</small></span></div><button type="button" onClick={() => setTeacherNoteDlg(null)} aria-label="关闭"><X size={17} /></button></header><div className="teacher-note-body"><label className="field-group"><span className="field-label">你的补充要求</span><textarea value={tnInstruction} onChange={(event) => setTnInstruction(event.target.value)} placeholder="例如：补充一个与C语言相关的知识点" rows={3} /></label><div className="teacher-note-actions"><button type="button" className="primary-button compact" disabled={tnBusy || !tnInstruction.trim()} onClick={() => void generateTeacherNote()}>{tnBusy ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />}dsh 生成</button></div>{tnGenerated && <><div className="teacher-note-preview-head">预览（可直接编辑后保存）</div><textarea className="teacher-note-preview" value={tnGenerated} onChange={(event) => setTnGenerated(event.target.value)} rows={12} /></>}</div><footer className="dialog-footer"><button type="button" className="secondary-button" onClick={() => setTeacherNoteDlg(null)}>取消</button>{tnGenerated && <button type="button" className="primary-button compact" disabled={tnBusy} onClick={() => void saveTeacherNote()}><Check size={15} />{tnGenerated && !tnEditing ? '同意导入（保存）' : '保存'}</button>}</footer></section></div>}
    {outlineHistoryOpen && outline && <div className="unit-dialog-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setOutlineHistoryOpen(false)}><section className="unit-dialog outline-history-dialog" role="dialog" aria-modal="true"><header><div><History size={18} /><span><strong>版本历史 · 知识大纲</strong><small>共 {outlines.filter((o) => o.id === outline.id).length} 个版本，可查看或删除任意版本（正被课程设计引用的版本受保护）</small></span></div><button type="button" onClick={() => setOutlineHistoryOpen(false)} aria-label="关闭"><X size={17} /></button></header><div className="outline-history-list">{outlines.filter((o) => o.id === outline.id).slice().sort((a, b) => b.version - a.version).map((o) => { const current = o.id === outline.id && o.version === outline.version; return <div key={`${o.id}:${o.version}`} className={`outline-history-row ${current ? 'is-current' : ''}`}><button type="button" className="outline-history-view" onClick={() => { selectOutline(o); setOutlineHistoryOpen(false); }}><strong>v{o.version}{o.status === 'confirmed' ? ' 已确认' : ' 草稿'}</strong><span>{o.nodes.length} 个知识点 · {formatDate(o.updated_at)}</span></button>{current ? <em className="outline-history-current">当前</em> : <button type="button" className="outline-history-del" title="删除该版本" onClick={() => setDialog({ mode: 'delete-outline', outline: o, allHistory: false })}><Trash2 size={14} /></button>}</div>; })}</div><footer className="outline-history-footer"><button type="button" className="secondary-button" onClick={() => setDialog({ mode: 'delete-outline', outline, allHistory: true })}><Trash2 size={14} />删除全部旧版本（保留最新）</button><button type="button" className="primary-button compact" onClick={() => setOutlineHistoryOpen(false)}>完成</button></footer></section></div>}
    {insertPicker && <div className="unit-dialog-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setInsertPicker(null)}><section className="gpi-dialog" role="dialog" aria-modal="true"><header className="gpi-header"><div className="gpi-header-title"><span className="gpi-app-icon"><BookOpen size={20} /></span><div><strong>图谱导入知识大纲</strong><span className="gpi-breadcrumb">{insertPicker.title} · 图谱节点关系与问答</span></div></div><div className="gpi-header-actions"><button type="button" className="gpi-btn gpi-btn-primary" disabled={mutating} onClick={() => { void importNodes(insertPicker.nodes.map((n) => n.id), insertPicker.nodeId); }}><Layers3 size={15} />一键导入全部（{insertPicker.nodes.length}）</button><button type="button" className="gpi-close" onClick={() => setInsertPicker(null)} aria-label="关闭"><X size={17} /></button></div></header>
      {insertPicker.nodes.length === 0 ? <p className="step-empty">本节暂无图谱节点</p> : (() => {
        const selected = insertPicker.nodes.find((n) => n.id === graphSelectedId) || insertPicker.nodes[0];
        const rootCount = insertPicker.nodes.filter((n) => !n.parent_id).length;
        const q = graphQuery.trim().toLowerCase();
        const matched = q ? insertPicker.nodes.filter((n) => n.title.toLowerCase().includes(q) || (n.section_title || '').toLowerCase().includes(q)) : insertPicker.nodes;
        const hasKid = (id: string) => insertPicker.nodes.some((n) => n.parent_id === id);
        const rawMd = (selected.content || '').replace(/^```(?:json|md|markdown)?\s*/m, '').replace(/\s*```\s*$/m, '');
        return (<>
      <div className="gpi-body">
        <aside className="gpi-side">
          <div className="gpi-side-filters"><div className="gpi-search"><Search size={14} /><input value={graphQuery} onChange={(event) => setGraphQuery(event.target.value)} placeholder="搜索节点名称" /></div></div>          <div className="gpi-tree">{matched.length === 0 ? <div className="gpi-tree-empty">没有匹配的节点</div> : (() => { const treeNodes: Array<{ node: typeof insertPicker.nodes[number]; depth: number }> = []; const add = (id: string, depth: number) => { const found = matched.find((n) => n.id === id); if (!found) return; treeNodes.push({ node: found, depth }); matched.filter((n) => n.parent_id === id).forEach((k) => add(k.id, depth + 1)); }; const shownIds = new Set(matched.map((n) => n.id)); const shownRoots = matched.filter((n) => !n.parent_id || !shownIds.has(n.parent_id)); shownRoots.forEach((r) => add(r.id, 0)); return treeNodes.map(({ node: t, depth }) => <div key={t.id} className="gpi-tree-row" style={{ paddingLeft: 10 + depth * 15 }}><button type="button" className={`gpi-tree-main ${graphSelectedId === t.id ? 'is-active' : ''}`} onClick={() => setGraphSelectedId(t.id)}><span className="gpi-tree-indent">{depth > 0 && <i className="gpi-tree-line" />}</span>{(depth === 0 ? <span className="gpi-tree-icon is-root"><BookOpen size={11} /></span> : <span className="gpi-tree-icon"><FileText size={11} /></span>)}<span className="gpi-tree-title">{t.title}</span>{hasKid(t.id) && <em className="gpi-tree-kids">{matched.filter((k) => k.parent_id === t.id).length}</em>}<label className="gpi-tree-check" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={graphImportSet.has(t.id)} onChange={() => setGraphImportSet((cur) => { const next = new Set(cur); if (next.has(t.id)) next.delete(t.id); else next.add(t.id); return next; })} /></label></button></div>); })()}</div>
          <div className="gpi-side-foot"><span>{rootCount} 个根 · {insertPicker.nodes.length - rootCount} 个节点 · 已选 {graphImportSet.size}</span></div>
        </aside>
        <main className="gpi-canvas">
          <GraphView nodes={insertPicker.nodes} selectedId={selected.id} onSelect={(id) => setGraphSelectedId(id)} zoom={graphZoom} onZoom={setGraphZoom} zoomResetToken={graphZoomToken} />
        </main>
        <aside className="gpi-detail">
          <div className="gpi-detail-head"><strong>节点详情</strong>{selected.parent_id && <small>子节点</small>}</div>
          <div className="gpi-detail-title">{(rawMd.match(/^##\s*(.+)$/m)?.[1] || selected.title) + ' · 主题'}</div>
          <div className="gpi-riche"><div className="gpi-riche-body">{(() => {
            if (!rawMd) return <span className="gpi-detail-empty">（无内容）</span>;
            const sections = Array.from(rawMd.matchAll(/^##\s+(.+)$/gm)).map((m) => ({ label: m[1].trim(), text: (() => { const start = (m.index || 0) + m[0].length; const next = rawMd.indexOf('\n## ', m.index || 0); return rawMd.slice(start, next > -1 ? next : undefined).trim(); })() })).filter((s) => s.text);
            return (sections.length ? sections : [{ label: '内容', text: rawMd }]).map((s, i) => <section key={s.label + i} className="gpi-sec is-open"><header><span className="gpi-sec-caret"><ChevronDown size={13} /></span><strong>{s.label}</strong></header><div className="gpi-sec-body">{s.text}</div></section>);
          })()}</div></div>
          <div className="gpi-detail-foot"><button type="button" className="gpi-btn gpi-btn-primary gpi-btn-block" disabled={mutating} onClick={() => { void mountGraphToNode(selected.id, insertPicker.nodeId).then(() => setInsertPicker(null)); }}><Check size={15} />导入此节点</button></div>
        </aside>
      </div>
      <div className="gpi-canvas-toolbar"><button type="button" className="gpi-icon-btn-on" title="缩小" onClick={() => setGraphZoom((z) => Math.max(0.5, z - 0.25))}><ZoomOut size={13} /></button><span className="gpi-zoomval">{Math.round(graphZoom * 100)}%</span><button type="button" className="gpi-icon-btn-on" title="放大" onClick={() => setGraphZoom((z) => Math.min(2.5, z + 0.25))}><ZoomIn size={13} /></button><span className="gpi-toolbar-sep" /><button type="button" className="gpi-icon-btn" title="适应画布" onClick={() => setGraphZoomToken((v) => v + 1)}><Maximize size={13} /></button></div>
    </>); })()}
    </section></div>}
  </div>;
}

function UnitDialog({ dialog, units, files, outlines, mutating, onChange, onClose, onSubmit }: { dialog: Dialog; units: MaterialUnitSummary[]; files: Array<MaterialUnitFileAnalysis & { sourceLabel: string }>; outlines: MaterialUnitKnowledgeOutline[]; mutating: boolean; onChange: (dialog: Dialog) => void; onClose: () => void; onSubmit: () => void }) {
  const target = dialog.mode === 'merge' || dialog.mode === 'link-files' ? dialog.target : dialog.mode === 'rename' || dialog.mode === 'delete' ? dialog.unit : null;
  const sources = target ? units.filter((item) => item.id !== target.id) : [];
  const selectedImportOutline = dialog.mode === 'import-design' ? outlines.find((item) => `${item.id}:${item.version}` === dialog.outlineKey) : null;
  const importFiles = files;
  const selectedImportFiles = dialog.mode === 'import-design' ? files.filter((file) => dialog.materialIds.includes(file.material_id)) : [];
  const primaryImportFile = dialog.mode === 'import-design' ? files.find((file) => file.material_id === dialog.primaryMaterialId) : null;
  const [sourceRecord, setSourceRecord] = useState<MaterialUnitRecord | null>(null);
  useEffect(() => { if (dialog.mode === 'link-files' && dialog.sourceUnitId) void materialUnitApi.get(dialog.sourceUnitId).then(setSourceRecord); else setSourceRecord(null); }, [dialog]);
  return <div className="unit-dialog-backdrop"><section className={`unit-dialog ${dialog.mode === 'import-design' ? 'is-wide' : ''}`} role="dialog" aria-modal="true"><header><div>{dialog.mode === 'merge' ? <GitMerge size={19} /> : dialog.mode === 'link-files' ? <Link2 size={19} /> : dialog.mode === 'delete' || dialog.mode === 'delete-outline' ? <Trash2 size={19} /> : dialog.mode === 'import-design' ? <Send size={19} /> : <Edit3 size={19} />}<span><strong>{dialog.mode === 'merge' ? '整合为一个单元' : dialog.mode === 'link-files' ? '关联其他单元资料' : dialog.mode === 'delete' ? '删除资料单元' : dialog.mode === 'delete-outline' ? '删除知识大纲' : dialog.mode === 'import-design' ? '确认导入课程设计' : '重命名资料单元'}</strong><small>{dialog.mode === 'merge' ? '来源单元会从列表移除，课程资料库原文件不会删除' : dialog.mode === 'link-files' ? '只建立文件引用，来源单元和原文件保持不变' : dialog.mode === 'delete' ? '只删除资料单元记录，不删除课程资料库原文件' : dialog.mode === 'delete-outline' ? '删除操作不会影响教材、进度表和教学大纲原文件' : dialog.mode === 'import-design' ? '请核对知识大纲版本、主教材和支撑资料；未解析材料会在导入前自动补齐解析' : '资料关系和分析结果保持不变'}</small></span></div><button type="button" onClick={onClose} aria-label="关闭"><X size={17} /></button></header>
    {dialog.mode === 'rename' && <label>单元名称<input autoFocus value={dialog.title} onChange={(event) => onChange({ ...dialog, title: event.target.value })} /></label>}
    {dialog.mode === 'delete' && target && <div className="dialog-warning"><strong>确认删除“{target.title}”？</strong><span>知识大纲和单元内整理关系会一并删除，但课程资料库和本机原文件不会删除。</span></div>}
    {dialog.mode === 'delete-outline' && <><div className="dialog-warning"><strong>{dialog.outline.title} · 第 {dialog.outline.version} 版</strong><span>{dialog.allHistory ? '将删除该知识大纲的全部历史版本。' : '只删除当前选中的历史版本；若它是最新版，上一版本将成为最新版。'}</span></div><label className="delete-history-option"><input type="checkbox" checked={dialog.allHistory} onChange={(event) => onChange({ ...dialog, allHistory: event.target.checked })} /><span><b>删除全部历史版本</b><small>课程设计正在引用的版本受保护，无法删除</small></span></label></>}
    {dialog.mode === 'import-design' && <div className="import-confirm-grid"><section><label>知识大纲版本<select value={dialog.outlineKey} onChange={(event) => onChange({ ...dialog, outlineKey: event.target.value })}>{outlines.slice().sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map((item) => <option key={`${item.id}:${item.version}`} value={`${item.id}:${item.version}`}>v{item.version} · {item.title} · {item.nodes.length} 个知识点</option>)}</select></label><div className="import-outline-summary"><BookOpen size={18} /><span><strong>{selectedImportOutline?.title}</strong><small>第 {selectedImportOutline?.version} 版 · {selectedImportOutline?.status === 'confirmed' ? '已确认' : '草稿'} · {selectedImportOutline?.nodes.length || 0} 个知识点</small></span></div></section><section><div className="dialog-section-title"><strong>教材与支撑资料</strong><span>已选 {dialog.materialIds.length} 份</span></div><div className="dialog-options import-files">{importFiles.map((file) => <label key={file.material_id} className={dialog.materialIds.includes(file.material_id) ? 'selected' : ''}><input type="checkbox" checked={dialog.materialIds.includes(file.material_id)} onChange={() => { const next = dialog.materialIds.includes(file.material_id) ? dialog.materialIds.filter((id) => id !== file.material_id) : [...dialog.materialIds, file.material_id]; const primary = next.includes(dialog.primaryMaterialId) ? dialog.primaryMaterialId : (files.find((item) => next.includes(item.material_id) && item.category === 'textbook')?.material_id || ''); onChange({ ...dialog, materialIds: next, primaryMaterialId: primary }); }} /><span><b>{file.name}</b><small>{categoryLabels[file.category] || file.category} · {file.character_count.toLocaleString()} 字 · {file.quality_level || file.parse_status} · {file.sourceLabel}</small>{file.parse_status !== 'parsed' && <em className="import-parse-flag">未解析，导入前将后台补齐</em>}</span></label>)}</div><label>主教材<select value={dialog.primaryMaterialId} onChange={(event) => onChange({ ...dialog, primaryMaterialId: event.target.value })}><option value="">请选择主教材</option>{selectedImportFiles.filter((file) => file.category === 'textbook').map((file) => <option key={file.material_id} value={file.material_id}>{file.name}</option>)}</select></label></section><aside><strong>导入摘要</strong><span>知识大纲 v{selectedImportOutline?.version || '-'}</span><span>{selectedImportOutline?.nodes.length || 0} 个知识点</span><span>{selectedImportFiles.filter((file) => file.category === 'textbook').length} 份教材</span><span>{selectedImportFiles.filter((file) => file.category !== 'textbook').length} 份支撑资料</span><small>{primaryImportFile ? `主教材：${primaryImportFile.name}` : '尚未指定主教材'}</small></aside></div>}
    {dialog.mode === 'merge' && <><label>整合后的名称<input value={dialog.title} onChange={(event) => onChange({ ...dialog, title: event.target.value })} /></label><div className="dialog-options"><strong>选择要整合的单元</strong>{sources.map((source) => <label key={source.id}><input type="checkbox" checked={dialog.sourceIds.includes(source.id)} onChange={() => onChange({ ...dialog, sourceIds: dialog.sourceIds.includes(source.id) ? dialog.sourceIds.filter((id) => id !== source.id) : [...dialog.sourceIds, source.id] })} /><span><b>{source.title}</b><small>{source.material_count} 份资料；整合后该单元会从列表移除</small></span></label>)}</div>{dialog.sourceIds.length > 0 && <div className="merge-impact"><strong>将发生以下变化</strong><span>当前单元与 {dialog.sourceIds.length} 个来源单元整合为“{dialog.title || dialog.target.title}”</span><span>{dialog.sourceIds.length} 个来源单元将从单元列表移除</span><span>课程资料库中的原始文件不会删除</span></div>}</>}
    {dialog.mode === 'link-files' && <><label>来源单元<select value={dialog.sourceUnitId} onChange={(event) => onChange({ ...dialog, sourceUnitId: event.target.value, materialIds: [] })}><option value="">请选择来源单元</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title}</option>)}</select></label>{sourceRecord && <div className="dialog-options"><strong>选择要关联的文件</strong>{sourceRecord.files.map((file) => <label key={file.material_id}><input type="checkbox" checked={dialog.materialIds.includes(file.material_id)} onChange={() => onChange({ ...dialog, materialIds: dialog.materialIds.includes(file.material_id) ? dialog.materialIds.filter((id) => id !== file.material_id) : [...dialog.materialIds, file.material_id] })} /><span><b>{file.name}</b><small>{categoryLabels[file.category] || file.category} · 关联后可用于匹配和细化</small></span></label>)}</div>}</>}
    <footer><button type="button" onClick={onClose}>取消</button><button type="button" className={dialog.mode === 'delete' || dialog.mode === 'delete-outline' ? 'danger' : 'primary'} disabled={mutating || (dialog.mode === 'rename' && !dialog.title.trim()) || (dialog.mode === 'merge' && !dialog.sourceIds.length) || (dialog.mode === 'link-files' && (!dialog.sourceUnitId || !dialog.materialIds.length)) || (dialog.mode === 'import-design' && (!dialog.outlineKey || !dialog.materialIds.length || !dialog.primaryMaterialId || primaryImportFile?.category !== 'textbook'))} onClick={onSubmit}>{mutating ? <Loader2 className="spin" size={15} /> : <Check size={15} />}{dialog.mode === 'merge' ? '确认整合' : dialog.mode === 'link-files' ? '确认关联' : dialog.mode === 'delete' || dialog.mode === 'delete-outline' ? '确认删除' : dialog.mode === 'import-design' ? '确认并进入课程设计' : '保存名称'}</button></footer>
  </section></div>;
}

function FilePreview({ file, onClose, parseProgress, rawText, rawPages, rawLoading, onReparse, unitId }: { file: MaterialUnitFileAnalysis; onClose: () => void; parseProgress?: { progress: number; status: string; materials: Array<{ id: string; name: string; status: string; progress: number; message: string }> } | null; rawText?: string | null; rawPages?: Array<{ page: number; text: string }> | null; rawLoading?: boolean; onReparse?: (engine: 'rapidocr' | 'mineru') => void; unitId?: string }) {
  const matching = parseProgress?.materials?.find((m) => m.id === file.material_id);
  const parsing = matching && ['running', 'pending', 'parsing'].includes(matching.status);
  const stateLabel = file.parse_status === 'parsed' ? `已提取 · ${file.character_count.toLocaleString()} 字` : file.parse_status === 'parse_failed' ? '提取失败' : file.parse_status === 'unsupported' ? '格式不支持' : parsing ? `解析中 ${Math.round(matching!.progress)}%` : '未提取 / 解析中…';
  const [reEngine, setReEngine] = useState<'rapidocr' | 'mineru'>('mineru');
  const docUrl = file.document_id ? documentApi.previewUrl(file.document_id!) : null;
  // M7 阅读图谱状态
  const [chatId, setChatId] = useState('');
  const [rounds, setRounds] = useState<Array<{ role: string; content: string }>>([]);
  const [question, setQuestion] = useState('');
  const [quote, setQuote] = useState('');
  const [graphBusy, setGraphBusy] = useState(false);
  const [graphNodes, setGraphNodes] = useState<Array<{ id: string; title: string; content: string; updated_at: string; parent_id?: string | null; section_title?: string }>>([]);
  // 每个图谱节点被导入到的大纲位置: nodeId -> [{outline_id, out线_version, outline_title, node_id, node_title, quote}]
  const [graphImports, setGraphImports] = useState<Record<string, Array<{ outline_id: string; outline_version: number; outline_title: string; node_id: string; node_title: string; quote: string }>>>({});
  const [graphError, setGraphError] = useState('');
  const [selectionText, setSelectionText] = useState('');
  const [contextNodeId, setContextNodeId] = useState('');  // 当前讨论是基于哪个图谱节点
  const [roundsTitle, setRoundsTitle] = useState('');      // 当前讨论的引用标题提示
  const loadNodes = useCallback(async () => {
    if (!unitId) return;
    try {
      const resp = await materialUnitApi.graphNodes(unitId, file.material_id);
      setGraphNodes(resp.items);
      // 并行查每个节点被导入到了哪些大纲位置
      const map: Record<string, Array<{ outline_id: string; outline_version: number; outline_title: string; node_id: string; node_title: string; quote: string }>> = {};
      await Promise.all(resp.items.map(async (n) => {
        try {
          const imp = await materialUnitApi.graphNodeOutlineImports(unitId, n.id);
          if (imp.items.length) map[n.id] = imp.items;
        } catch (_e) { /* 忽略单节点失败 */ }
      }));
      setGraphImports(map);
    } catch (_e) { /* 忽略 */ }
  }, [unitId, file.material_id]);
  useEffect(() => { void loadNodes(); }, [loadNodes]);
  // 重开/再次进入时: 恢复最近一次的读图对话(问题+回答+"基于节点")，
  // 避免"思考中关闭后再进"看到空白 — 与后端"先落库问题再回答"配合:
  const restoreChat = useCallback(async () => {
    if (!unitId) return;
    try {
      const resp = await materialUnitApi.graphChats(unitId, file.material_id);
      const latest = resp.items?.[0];
      if (!latest || !latest.rounds?.length) return;
      setChatId(latest.id);
      setRounds(latest.rounds);
      // 若最后一轮是 user(回答还没回来/思考中关闭), 把问题放回输入框, 用户可重发或续聊
      const lastC = latest.rounds[latest.rounds.length - 1];
      const lastIsQ = lastC?.role === 'user';
      if (lastIsQ && !question) setQuestion(lastC.content);
      if (latest.context_node_id) {
        setContextNodeId(latest.context_node_id);
        const parent = graphNodes.find((n) => n.id === latest.context_node_id);
        setRoundsTitle(parent ? `基于「${parent.title}」` : '基于图谱节点讨论');
      }
    } catch (_e) { /* 忽略: 无历史或加载失败不打断预览 */ }
  }, [unitId, file.material_id]);
  useEffect(() => { void restoreChat(); }, [restoreChat]);
  const sendGraph = async () => {
    if (!unitId || !question.trim()) return;
    setGraphBusy(true); setGraphError('');
    try {
      const resp = await materialUnitApi.graphChat(unitId, { material_id: file.material_id, question: question.trim(), quote: quote || undefined, chat_id: chatId || undefined, context_node_id: contextNodeId || undefined });
      setChatId(resp.chat_id);
      setRounds((cur) => [...cur, { role: 'user', content: resp.question }, { role: 'assistant', content: resp.answer }]);
      if (!roundsTitle && contextNodeId) {
        const parent = graphNodes.find((n) => n.id === contextNodeId);
        if (parent) setRoundsTitle(`基于「${parent.title}」`);
      }
      setQuestion('');
    } catch (reason) { setGraphError(getErrorMessage(reason)); }
    finally { setGraphBusy(false); }
  };
  const clearGraph = async () => {
    if (!unitId || !chatId) return;
    try { await materialUnitApi.graphChatClear(unitId, chatId); setRounds([]); setChatId(''); setContextNodeId(''); setRoundsTitle(''); }
    catch (reason) { setGraphError(getErrorMessage(reason)); }
  };
  const saveGraphNote = async () => {
    if (!unitId || !chatId || !rounds.length) return;
    setGraphBusy(true); setGraphError('');
    try {
      const resp = await materialUnitApi.graphChatSave(unitId, chatId, undefined, contextNodeId || undefined);
      void resp;
      await loadNodes();
      setGraphError('');
    } catch (reason) { setGraphError(getErrorMessage(reason)); }
    finally { setGraphBusy(false); }
  };
  const L = { drawer: { width: '100%', height: '100%', background: '#f7f7f8', color: '#1f2329', border: 0, boxShadow: '0 22px 64px rgba(0,0,0,.22)', overflow: 'hidden', display: 'flex', flexDirection: 'column' as const, fontFamily: 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif' },
    header: { padding: '12px 16px', borderBottom: '1px solid #e3e4e8', background: '#f2f3f5', display: 'flex', alignItems: 'center', gap: 10 },
    body: { flex: 1, display: 'flex', minHeight: 0 },
    col: { flex: 1, minWidth: 280, overflow: 'auto', padding: 14, borderRight: '1px solid #e3e4e8', background: '#fff' },
    colHead: { fontSize: 13, fontWeight: 700, color: '#1f2329', marginBottom: 8, paddingBottom: 6, borderBottom: '2px solid #3b82f6' },
    text: { fontSize: 12.5, lineHeight: 1.85, color: '#374151', whiteSpace: 'pre-wrap' as const, wordBreak: 'break-word' as const },
    muted: { fontSize: 12, color: '#9ca3af' },
    graphBox: { marginTop: 12, border: '1px solid #dbe4ee', borderRadius: 8, background: '#fbfdff', padding: 10, display: 'grid', gap: 8 },
    graphHead: { display: 'flex', alignItems: 'center', gap: 6, color: '#1f4e8c', fontSize: 12, fontWeight: 700 },
    graphQuote: { padding: '5px 7px', border: '1px dashed #b6cdea', borderRadius: 5, color: '#365e94', background: '#f2f8ff', fontSize: 11, lineHeight: 1.5 },
    graphInput: { minHeight: 30, padding: '5px 7px', border: '1px solid #ccd8e5', borderRadius: 5, fontSize: 12 },
    graphBtn: { minHeight: 27, padding: '0 8px', borderRadius: 5, fontSize: 11.5, border: '1px solid #b6cdea', background: '#eef6ff', color: '#1857b7', cursor: 'pointer' },
    graphBtn2: { minHeight: 27, padding: '0 8px', borderRadius: 5, fontSize: 11.5, border: '1px solid #d8e0ea', background: '#fff', color: '#52677f', cursor: 'pointer' } };
  // 从 rawPages 选中文本的辅助(选词加入讨论)
  const addQuote = (text: string) => { setQuote(text.slice(0, 400)); setGraphError(''); };
  return <div className="file-preview-backdrop"><aside style={L.drawer}>
    <header style={L.header}><span style={{ background: '#3b82f6', color: '#fff', fontSize: 11, padding: '2px 8px', borderRadius: 999 }}>{categoryLabels[file.category] || file.category}</span><strong style={{ fontSize: 13.5 }}>{file.name}</strong><small style={{ ...L.muted, color: '#6b7280' }}>{file.path}</small><span style={{ flex: 1 }} /><button type="button" onClick={onClose} aria-label="关闭" style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#4b5563' }}><X size={17} /></button></header>
    <div style={L.body}>
      <section style={{ ...L.col, minWidth: 340 }}>
        <div style={L.colHead}>识别情况</div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12.5, marginBottom: 10 }}><span style={{ width: 8, height: 8, borderRadius: 99, background: file.parse_status === 'parsed' ? '#22c55e' : file.parse_status === 'parse_failed' ? '#ef4444' : file.parse_status === 'unsupported' ? '#9ca3af' : '#f59e0b' }} />{stateLabel}{file.extraction_engine ? <span style={L.muted}> · {file.extraction_engine}</span> : null}</div>
        {parsing && <div style={{ marginBottom: 10 }}><div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#6b7280', marginBottom: 3 }}><span>{matching!.message || `解析中 ${Math.round(matching!.progress)}%`}</span><strong>{Math.round(matching!.progress)}%</strong></div><progress value={matching!.progress} max={100} style={{ width: '100%', height: 8 }} /></div>}
        <p style={L.text}>{file.summary || file.parse_message || '暂无摘要'}</p>
        {file.knowledge_points.length > 0 && <div style={{ marginTop: 10 }}><h5 style={{ margin: '0 0 4px', fontSize: 12, color: '#1f2329' }}>识别知识点</h5><div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 6 }}>{file.knowledge_points.map((point) => <span key={point} style={{ fontSize: 11, background: '#eef2ff', color: '#3730a3', borderRadius: 6, padding: '2px 7px' }}>{point}</span>)}</div></div>}
        <dl style={{ margin: '12px 0 0', fontSize: 12 }}><div style={{ display: 'flex', gap: 8, padding: '3px 0' }}><dt style={{ color: '#6b7280', minWidth: 60 }}>解析引擎</dt><dd style={{ margin: 0 }}>{file.extraction_engine || '未执行'}</dd></div><div style={{ display: 'flex', gap: 8, padding: '3px 0' }}><dt style={{ color: '#6b7280', minWidth: 60 }}>识别质量</dt><dd style={{ margin: 0 }}>{file.quality_level || '未评估'}</dd></div><div style={{ display: 'flex', gap: 8, padding: '3px 0' }}><dt style={{ color: '#6b7280', minWidth: 60 }}>内容规模</dt><dd style={{ margin: 0 }}>{file.character_count.toLocaleString()} 字 · {file.section_count} 个分区</dd></div></dl>
        <div style={{ marginTop: 14 }}><div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4 }}>重新识别（可选引擎）</div><div style={{ display: 'flex', gap: 6 }}><select value={reEngine} onChange={(e) => setReEngine(e.target.value as 'rapidocr' | 'mineru')} disabled={parsing} style={{ fontSize: 12, padding: '3px 6px', border: '1px solid #d1d5db', borderRadius: 6, background: '#fff' }}><option value="rapidocr">RapidOCR（快）</option><option value="mineru">MinerU（版面更准）</option></select><button type="button" disabled={parsing} onClick={() => onReparse?.(reEngine)} style={{ fontSize: 12, padding: '3px 12px', border: '1px solid #3b82f6', color: '#1d4ed8', background: '#eff6ff', borderRadius: 6, cursor: parsing ? 'default' : 'pointer' }}>{parsing ? '识别中…' : '重新识别并保存'}</button></div></div>
        {/* M7: 阅读图谱（教材研读 AI 讨论 → 图谱节点） */}
        <div style={L.graphBox}>
          <div style={L.graphHead}>📖 阅读图谱 <small style={{ color: '#8190a0', fontWeight: 400 }}>教材研读 · dsh</small></div>
          {roundsTitle && <div style={{ fontSize: 11, color: '#8190a0' }}>▾ {roundsTitle}</div>}
          <div style={L.graphQuote}>{quote ? `引用: ${quote}` : contextNodeId ? '基于图谱节点讨论（上下文=该节点+教材）' : '在右侧「解析后文本」选中一句话，点「➕加入讨论」即可引用'}</div>
          {rounds.length > 0 && <div style={{ display: 'grid', gap: 6, maxHeight: 300, overflow: 'auto' }}>{rounds.map((t, i) => <div key={i} style={{ fontSize: 11.5, lineHeight: 1.7, color: t.role === 'user' ? '#1f4e8c' : '#374151', background: t.role === 'user' ? '#eef6ff' : '#f4f7fa', borderRadius: 5, padding: '6px 8px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}><b>{t.role === 'user' ? '教师' : '助手'}</b> {(t.content || '').replace(/^```(?:md|markdown)?\s*/m, '').replace(/\s*```\s*$/m, '').slice(0, 900)}</div>)}</div>}
          <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="输入讨论问题，如：这里的易错点？" style={L.graphInput} />
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' as const }}>
            <button type="button" onClick={() => void sendGraph()} disabled={graphBusy || !question.trim()} style={L.graphBtn}>{graphBusy ? '思考中…' : '发送'}</button>
            <button type="button" onClick={() => { setQuote(''); setQuestion(''); setContextNodeId(''); setRoundsTitle(''); }} style={L.graphBtn2}>清空</button>
            {chatId && rounds.length > 0 && <button type="button" onClick={() => void clearGraph()} style={L.graphBtn2}>清空历史</button>}
            <button type="button" onClick={() => void saveGraphNote()} disabled={graphBusy || !rounds.length} style={L.graphBtn}>💾 保存为图谱节点{contextNodeId ? '(子节点)' : ''}</button>
          </div>
          {graphError && <div style={{ color: '#b3352c', fontSize: 11 }}>{graphError}</div>}
          {graphNodes.length > 0 && <details style={{ borderTop: '1px solid #e3e9f1', paddingTop: 6 }}><summary style={{ fontSize: 11.5, color: '#52677f', cursor: 'pointer' }}>已保存图谱节点（{graphNodes.length}）</summary><div style={{ display: 'grid', gap: 6, marginTop: 6 }}>{[...graphNodes].sort((a, b) => (a.parent_id ? 1 : 0) - (b.parent_id ? 1 : 0)).map((node) => <div key={node.id} style={{ border: '1px solid #dbe4ee', borderRadius: 5, padding: 6, background: '#fff', marginLeft: node.parent_id ? 12 : 0 }}><div style={{ display: 'flex', alignItems: 'center', gap: 5 }}><b style={{ fontSize: 11.5, color: '#1f4e8c', flex: 1 }}>{node.parent_id ? '└ ' : ''}{node.title}</b>{node.section_title && <small style={{ color: '#8190a0', fontSize: 10 }}>{node.section_title.slice(0, 18)}</small>}<button type="button" title="基于此讨论" onClick={() => { setContextNodeId(node.id); setRoundsTitle(`基于「${node.title}」`); setQuote(''); setQuestion(''); setChatId(''); setRounds([]); }} style={{ ...L.graphBtn, minWidth: 22, padding: '0 5px' }}>💬</button><button type="button" title="删除" onClick={() => { if (window.confirm(`删除图谱节点「${node.title}」及子节点？`)) void materialUnitApi.graphNodeDelete(unitId!, node.id).then(() => void loadNodes()).catch((reason) => setGraphError(getErrorMessage(reason))); }} style={{ ...L.graphBtn2, minWidth: 20, padding: '0 5px', color: '#b3352c' }}><X size={12} /></button></div><pre style={{ margin: '4px 0 0', fontSize: 10.5, color: '#52677f', whiteSpace: 'pre-wrap', maxHeight: 110, overflow: 'auto' }}>{(node.content || '').replace(/^```(?:json|md|markdown)?\s*/m, '').replace(/\s*```\s*$/m, '').slice(0, 400)}</pre>{(() => { const imps = graphImports[node.id] || []; return imps.length ? <div style={{ marginTop: 5, borderTop: '1px solid #edf1f5', paddingTop: 5 }}><small style={{ color: '#6b7e93', fontSize: 10.5, display: 'block', marginBottom: 4 }}>📌 已导入到知识大纲（{imps.length} 处）</small>{imps.map((imp, ii) => <div key={ii} style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '2px 0' }}><span style={{ flex: 1, fontSize: 10.5, color: '#40546d', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>v{imp.outline_version} · {imp.node_title}</span><button type="button" title={`取消导入 （${imp.node_title}）`} onClick={() => { if (window.confirm(`取消导入「${imp.node_title}」的这份教材研读补充？`)) void materialUnitApi.graphNodeUnlinkOutline(unitId!, node.id, { outline_id: imp.outline_id, node_id: imp.node_id }).then(() => void loadNodes()).catch((reason) => setGraphError(getErrorMessage(reason))); }} style={{ ...L.graphBtn2, minWidth: 20, padding: '0 5px', color: '#b3352c' }}><Unlink size={11} /></button></div>)}</div> : <small style={{ color: '#8190a0', fontSize: 10.5 }}>在右侧知识大纲点击「📖 教材研读」挂载到对应章节</small>; })()}</div>)}</div></details>}
        </div>
      </section>
      <section style={{ ...L.col, display: 'flex', flexDirection: 'column' as const, overflow: 'hidden' }}><div style={L.colHead}>原文展示（原页）</div>{docUrl ? <iframe title="原页预览" src={docUrl} style={{ flex: 1, width: '100%', minHeight: 360, border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff' }} /> : <p style={L.muted}>该格式暂无原页预览</p>}</section>
      <section style={L.col}><div style={L.colHead}>解析后文本（页对齐）</div><div style={{ position: 'sticky', top: 0, zIndex: 3, display: 'flex', gap: 5, alignItems: 'center', padding: '4px 0', background: '#fff' }}>{selectionText && <button type="button" onClick={() => { addQuote(selectionText); setSelectionText(''); }} style={{ ...L.graphBtn, fontSize: 11 }}>➕ 加入讨论</button>}{selectionText && <small style={{ color: '#8190a0', fontSize: 10.5, maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{selectionText.slice(0, 40)}</small>}</div>{rawLoading ? <p style={L.muted}>正在加载解析文本…</p> : rawPages && rawPages.length ? <div style={L.text} className="parse-text-view page-aligned" onMouseUp={() => { const sel = window.getSelection()?.toString().trim() || ''; if (sel.length >= 4 && sel.length <= 400) setSelectionText(sel); else setSelectionText(''); }}>{rawPages.map((p) => <div key={p.page} id={`parse-page-${p.page}`} style={{ paddingBottom: 12, marginBottom: 12 }}><div style={{ fontSize: 10, color: '#3b82f6', fontWeight: 700, marginBottom: 3, borderBottom: '1px dashed #cbd5e1', paddingBottom: 3 }}>■ 第 {p.page} 页</div><span>{p.text}</span></div>)}</div> : rawText ? <div style={L.text} className="parse-text-view" onMouseUp={() => { const sel = window.getSelection()?.toString().trim() || ''; if (sel.length >= 4 && sel.length <= 400) setSelectionText(sel); else setSelectionText(''); }}>{rawText}</div> : <p style={L.muted}>（无解析文本，可点左侧"重新识别"）</p>}</section>
    </div>
  </aside></div>;
}
