import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle, Archive, CalendarDays, Check, CheckCircle2, ChevronDown, ChevronRight, Copy, Database,
  ExternalLink, File, FileSearch, Folder, FolderOpen, FolderPlus, FolderSync,
  Home, ListFilter, Loader2, MoreHorizontal, Move, PackagePlus, Pencil, RefreshCw,
  RotateCw, Search, Square, Tags, Trash2, Upload, X,
} from 'lucide-react';
import { courseArchiveApi, dataHubApi, getErrorMessage, materialUnitApi } from '../lib/api';
import type { ArchiveDeletionImpact, ArchiveDeletionResult, CourseArchiveSummary, DataHubBlock, DataHubCatalog, DataHubFolder, DataHubUnit, LocalSourceDiffResult, MaterialUnitSummary } from '../types/workflow';
import './DataHubWorkspace.css';

interface Props {
  archives: CourseArchiveSummary[];
  onOpenArchive: (archiveId: string) => void;
  onDataChanged: () => void;
  onImportFolder: (files: File[], archiveId?: string | null, sourceId?: string | null, sourceName?: string, onProgress?: (done: number, total: number) => void, directoryPaths?: string[], parentFolderId?: string | null) => Promise<{ archiveId: string; sourceId: string } | null>;
  onDeleteArchive: (archiveId: string) => Promise<ArchiveDeletionResult | null>;
  onMaterialUnitImported: () => void;
}

type PreviewTab = 'original' | 'metadata';
type SortMode = 'category' | 'date';
type DirectoryEntry =
  | { type: 'folder'; name: string; count: number; kinds: Set<DataHubBlock['kind']>; customId?: string }
  | { type: 'file'; block: DataHubBlock };
type DirectoryTreeNode = { name: string; path: string[]; children: DirectoryTreeNode[] };
type PickedDirectory = { rootName: string; files: File[]; directoryPaths: string[] };
type PendingLocalSync =
  | {
      id: string;
      kind: 'folder';
      unitId: string;
      archiveId: string;
      folderId: string;
      label: string;
      pathLabel: string;
    }
  | {
      id: string;
      kind: 'upload';
      unitId: string;
      archiveId: string;
      folderId: string;
      browserSourceId: string;
      rootName: string;
      files: File[];
      directoryPaths: string[];
      label: string;
      pathLabel: string;
    };
type PickerEntry = PickerFileEntry | PickerDirectoryEntry;
type PickerFileEntry = { kind: 'file'; name: string; getFile: () => Promise<File> };
type PickerDirectoryEntry = { kind: 'directory'; name: string; values: () => AsyncIterableIterator<PickerEntry> };
type OrganizeDialog =
  | { mode: 'create-root'; name: string }
  | { mode: 'rename-root'; name: string; archiveId: string; currentName: string }
  | { mode: 'create'; name: string; parentId: string | null; systemParent: DataHubBlock['kind'] | null; parentLabel: string }
  | { mode: 'rename-folder'; name: string; folder: DataHubFolder }
  | { mode: 'move-folder'; destination: string; folder: DataHubFolder }
  | { mode: 'delete-folder'; folder: DataHubFolder }
  | { mode: 'delete-source'; folder: DataHubFolder }
  | { mode: 'delete-blocks'; blocks: DataHubBlock[] }
  | { mode: 'rename-block'; name: string; block: DataHubBlock }
  | { mode: 'move-blocks'; destination: string; blocks: DataHubBlock[]; syncMode: 'platform' | 'copy' | 'move' };
type MaterialImportDialog = { blocks: DataHubBlock[]; previewId: string; mode: 'create' | 'append'; title: string; targetUnitId: string };

const kindLabels: Record<DataHubBlock['kind'], string> = {
  original: '原始文件', extracted: '提取正文', teaching_design: '教学设计', student_question: '学生问题',
  teacher_answer: '教师答疑', supervisor_review: '督导建议', ideological_element: '思政元素', imported: '导入内容',
};

const kindFolders: Record<DataHubBlock['kind'], string> = {
  original: '原始资料', extracted: '提取正文', teaching_design: '教学设计', student_question: '师生讨论',
  teacher_answer: '师生讨论', supervisor_review: '督导建议', ideological_element: '思政元素', imported: '资料包内容',
};

const fileKindOrder: DataHubBlock['kind'][] = ['original'];
const categoryLabels: Record<string, string> = {
  syllabus: '教学大纲', schedule: '进度表', textbook: '教材', courseware: '课件', lesson_plan: '教案',
  experiment: '实验', code: '代码', teaching_record: '教学记录', review: '审核材料', interactive: '交互资源',
  reference: '参考资料', media: '媒体', other: '其他',
};

function formatDate(value: string) {
  if (!value) return '未记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(date);
}

function timestampOf(value: number | string | null | undefined, fallback: string) {
  if (typeof value === 'number') return value;
  const parsed = new Date(value || fallback).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

function extensionOf(title: string) {
  const match = title.replace(/ · 提取正文$/, '').match(/\.([^.]+)$/);
  return match?.[1]?.slice(0, 5).toUpperCase() || 'DATA';
}

function pathForBlock(block: DataHubBlock, folderPaths: Map<string, string[]>): string[] {
  const customPath = block.folder_id ? folderPaths.get(block.folder_id) : undefined;
  if (customPath) return [...customPath, block.title];
  const folder = kindFolders[block.kind];
  if (block.kind !== 'original') return [folder, block.title];
  if (block.source_selection_kind === 'files') return [block.title];
  const locatorParts = block.locator.replace(/\\/g, '/').split('/').filter((part, index, parts) => part && part !== '.' && (index === 0 || part !== parts[index - 1]));
  return locatorParts.length ? [...locatorParts.slice(0, -1), block.title] : [block.title];
}

function startsWithPath(parts: string[], prefix: string[]) {
  return prefix.every((part, index) => parts[index] === part);
}

function pathKey(parts: string[]) {
  return parts.join('\u0000');
}

function materialIdOf(block: DataHubBlock) {
  const parts = block.id.split(':');
  return parts.length === 4 && parts[0] === 'material' ? parts[2] : null;
}

async function pickBrowserDirectory(): Promise<PickedDirectory | null | undefined> {
  const picker = (window as unknown as { showDirectoryPicker?: () => Promise<PickerDirectoryEntry> }).showDirectoryPicker;
  if (!picker) return undefined;
  try {
    const root = await picker.call(window);
    const files: File[] = [];
    const directoryPaths: string[] = [];
    const visit = async (directory: PickerDirectoryEntry, prefix: string) => {
      for await (const entry of directory.values()) {
        const relativePath = prefix ? `${prefix}/${entry.name}` : entry.name;
        if (entry.kind === 'directory') {
          directoryPaths.push(relativePath);
          await visit(entry, relativePath);
          continue;
        }
        const original = await entry.getFile();
        const file = new globalThis.File([original], original.name, { type: original.type, lastModified: original.lastModified });
        Object.defineProperty(file, 'webkitRelativePath', { configurable: true, value: `${root.name}/${relativePath}` });
        files.push(file);
      }
    };
    await visit(root, '');
    return { rootName: root.name, files, directoryPaths };
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') return null;
    throw reason;
  }
}

export function DataHubWorkspace({ archives, onOpenArchive, onDataChanged, onImportFolder, onDeleteArchive, onMaterialUnitImported }: Props) {
  const folderInput = useRef<HTMLInputElement | null>(null);
  const fileUploadInput = useRef<HTMLInputElement | null>(null);
  const directoryUploadInput = useRef<HTMLInputElement | null>(null);
  const refreshFileInput = useRef<HTMLInputElement | null>(null);
  const localSyncDialog = useRef<HTMLElement | null>(null);
  const sourceDiffDialog = useRef<HTMLElement | null>(null);
  const organizeDialogElement = useRef<HTMLElement | null>(null);
  const archiveDeleteDialogElement = useRef<HTMLElement | null>(null);
  const materialImportDialogElement = useRef<HTMLElement | null>(null);
  const catalogSummary = useRef<DataHubCatalog | null>(null);
  const unitRequestSequence = useRef(0);
  const initialLoadStarted = useRef(false);
  const [catalog, setCatalog] = useState<DataHubCatalog | null>(null);
  const [query, setQuery] = useState('');
  const [kindFilter, setKindFilter] = useState<DataHubBlock['kind'] | ''>('');
  const [sortMode, setSortMode] = useState<SortMode>('category');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [unit, setUnit] = useState<DataHubUnit | null>(null);
  const [currentPath, setCurrentPath] = useState<string[]>([]);
  const [block, setBlock] = useState<DataHubBlock | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [previewTab, setPreviewTab] = useState<PreviewTab>('original');
  const [expandedFolderPaths, setExpandedFolderPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [unitLoading, setUnitLoading] = useState(false);
  const [blockLoading, setBlockLoading] = useState(false);
  const [localSyncOpen, setLocalSyncOpen] = useState(false);
  const [pendingLocalSyncs, setPendingLocalSyncs] = useState<PendingLocalSync[]>([]);
  const [localSyncing, setLocalSyncing] = useState(false);
  const [sourceDiff, setSourceDiff] = useState<LocalSourceDiffResult | null>(null);
  const [sourceDiffLoading, setSourceDiffLoading] = useState(false);
  const [sourceReconciling, setSourceReconciling] = useState<'update_platform' | 'update_local' | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [organizeDialog, setOrganizeDialog] = useState<OrganizeDialog | null>(null);
  const [itemMenu, setItemMenu] = useState<{ type: 'folder' | 'block'; id: string } | null>(null);
  const organizeOpen = organizeDialog !== null;
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [archiveDelete, setArchiveDelete] = useState<{ archive: CourseArchiveSummary; impact: ArchiveDeletionImpact | null } | null>(null);
  const [archiveDeleteLoading, setArchiveDeleteLoading] = useState(false);
  const [archiveDeleting, setArchiveDeleting] = useState(false);
  const [pendingUploadRefresh, setPendingUploadRefresh] = useState<{ archiveId: string; sourceId: string; sourceName: string; selectionKind: 'files' | 'folder' } | null>(null);
  const [sourceUploadProgress, setSourceUploadProgress] = useState({ done: 0, total: 0 });
  const [materialImportDialog, setMaterialImportDialog] = useState<MaterialImportDialog | null>(null);
  const [materialUnits, setMaterialUnits] = useState<MaterialUnitSummary[]>([]);
  const [materialUnitsLoading, setMaterialUnitsLoading] = useState(false);
  const [materialImportPreviewLoading, setMaterialImportPreviewLoading] = useState(false);
  const [materialImporting, setMaterialImporting] = useState(false);
  const [parseTask, setParseTask] = useState<{ taskId: string; progress: number; status: string; materials: Array<{ id: string; name: string; status: string; progress: number; message: string }> } | null>(null);

  const startedParse = async (unitId: string, materialIds: string[]) => {
    try {
      const started = await materialUnitApi.parseTask(unitId, materialIds);
      if (!started?.task_id) return;
      setParseTask({ taskId: started.task_id, progress: 0, status: 'running', materials: [] });
      const tick = async () => {
        try {
          const st = await materialUnitApi.parseTaskStatus(unitId, started.task_id);
          setParseTask({ taskId: started.task_id, progress: st.progress, status: st.status, materials: st.materials || [] });
          if (st.status !== 'completed' && st.status !== 'failed') setTimeout(tick, 1500);
        } catch (_e) { /* 轮询失败忽略, 下次重试 */ }
      };
      setTimeout(tick, 1200);
    } catch (_e) { /* 后台解析启动失败不影响导入成功 */ }
  };
  const [materialImportElapsed, setMaterialImportElapsed] = useState(0);

  const loadUnitCatalog = async (nextUnit: DataHubUnit, summary: DataHubCatalog) => {
    const sequence = ++unitRequestSequence.current;
    setUnitLoading(true);
    try {
      const detail = await dataHubApi.catalog({ unit_id: nextUnit.id });
      if (sequence !== unitRequestSequence.current) return;
      setCatalog({ ...summary, folders: detail.folders, blocks: detail.blocks });
      setSelectedIds((current) => current.filter((id) => detail.blocks.some((item) => item.id === id)));
      setBlock((current) => current && detail.blocks.some((item) => item.id === current.id) ? current : null);
    } catch (reason) {
      if (sequence === unitRequestSequence.current) setError(getErrorMessage(reason));
    } finally {
      if (sequence === unitRequestSequence.current) setUnitLoading(false);
    }
  };

  const refresh = async (preferredArchiveId?: string) => {
    setLoading(true); setError('');
    try {
      unitRequestSequence.current += 1;
      const result = await dataHubApi.catalog({ summary_only: true });
      catalogSummary.current = result;
      const firstUnit = result.units.find((item) => item.archive_id === preferredArchiveId && item.id === unit?.id)
        || result.units.find((item) => item.archive_id === preferredArchiveId)
        || result.units.find((item) => item.id === unit?.id)
        || result.units[0]
        || null;
      setCatalog(result);
      setUnit(firstUnit);
      setLoading(false);
      if (firstUnit) await loadUnitCatalog(firstUnit, result);
      else setSelectedIds([]);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    void refresh();
  }, []);
  useEffect(() => {
    if (!localSyncOpen) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    localSyncDialog.current?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !localSyncing) setLocalSyncOpen(false);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => { document.removeEventListener('keydown', closeOnEscape); previousFocus?.focus(); };
  }, [localSyncOpen, localSyncing]);
  useEffect(() => {
    if (!sourceDiff) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    sourceDiffDialog.current?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !sourceReconciling) setSourceDiff(null);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => { document.removeEventListener('keydown', closeOnEscape); previousFocus?.focus(); };
  }, [sourceDiff, sourceReconciling]);
  useEffect(() => {
    if (!filtersOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFiltersOpen(false);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [filtersOpen]);
  useEffect(() => {
    if (!organizeOpen) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = organizeDialogElement.current;
    (dialog?.querySelector<HTMLElement>('[data-dialog-initial-focus]')
      || dialog?.querySelector<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled])'))?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOrganizeDialog(null);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => { document.removeEventListener('keydown', handleKeyDown); previousFocus?.focus(); };
  }, [organizeOpen]);
  useEffect(() => { setItemMenu(null); }, [currentPath, unit?.id]);

  useEffect(() => {
    if (!materialImporting) { setMaterialImportElapsed(0); return; }
    const started = Date.now();
    const timer = window.setInterval(() => setMaterialImportElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [materialImporting]);

  useEffect(() => {
    if (!materialImportDialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    materialImportDialogElement.current?.querySelector<HTMLElement>('input, select, button:not([disabled])')?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !materialImporting) setMaterialImportDialog(null);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => { document.removeEventListener('keydown', closeOnEscape); previousFocus?.focus(); };
  }, [!!materialImportDialog, materialImporting]);

  useEffect(() => {
    if (!archiveDelete) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    archiveDeleteDialogElement.current?.querySelector<HTMLElement>('input, button:not([disabled])')?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !archiveDeleting) setArchiveDelete(null);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => { document.removeEventListener('keydown', closeOnEscape); previousFocus?.focus(); };
  }, [archiveDelete, archiveDeleting]);

  const libraryRoots = useMemo(() => (catalog?.units || [])
    .map((item) => ({ unit: item, archive: archives.find((archive) => archive.id === item.archive_id) }))
    .sort((a, b) => a.unit.archive_name.localeCompare(b.unit.archive_name, 'zh-CN', { numeric: true })), [archives, catalog]);

  const unitBlocks = useMemo(() => (catalog?.blocks || []).filter((item) => {
    if (unit && item.unit_id !== unit.id) return false;
    return item.kind === 'original' && (!kindFilter || item.kind === kindFilter);
  }), [catalog, kindFilter, unit]);

  const unitFolders = useMemo(() => {
    const folders = (catalog?.folders || []).filter((item) => item.unit_id === unit?.id);
    const byId = new Map(folders.map((item) => [item.id, item]));
    return folders.filter((folder) => {
      let root = folder;
      const visited = new Set<string>();
      while (root.parent_id && byId.has(root.parent_id) && !visited.has(root.id)) {
        visited.add(root.id);
        root = byId.get(root.parent_id)!;
      }
      return !root.system_parent || root.system_parent === 'original';
    });
  }, [catalog, unit?.id]);
  const mountedSourceRoot = useMemo(() => {
    const sourceRoots = unitFolders.filter((folder) => !folder.parent_id && !!folder.source_folder_id);
    return sourceRoots.length === 1 ? sourceRoots[0] : null;
  }, [unitFolders]);
  const folderPaths = useMemo(() => {
    const folders = new Map(unitFolders.map((item) => [item.id, item]));
    const paths = new Map<string, string[]>();
    const resolve = (folder: DataHubFolder, visiting = new Set<string>()): string[] => {
      const cached = paths.get(folder.id);
      if (cached) return cached;
      if (visiting.has(folder.id)) return [folder.name];
      visiting.add(folder.id);
      const parent = folder.parent_id ? folders.get(folder.parent_id) : null;
      const prefix = parent ? resolve(parent, visiting) : folder.system_parent && folder.system_parent !== 'original' ? [kindFolders[folder.system_parent]] : [];
      const value = folder.id === mountedSourceRoot?.id ? [] : [...prefix, folder.name];
      paths.set(folder.id, value);
      return value;
    };
    unitFolders.forEach((folder) => resolve(folder));
    return paths;
  }, [mountedSourceRoot?.id, unitFolders]);
  const folderByPath = useMemo(() => new Map(unitFolders.map((folder) => [pathKey(folderPaths.get(folder.id) || [folder.name]), folder])), [folderPaths, unitFolders]);
  const folderNavigationTree = useMemo<DirectoryTreeNode[]>(() => {
    type MutableNode = { name: string; path: string[]; children: Map<string, MutableNode> };
    const roots = new Map<string, MutableNode>();
    const addPath = (parts: string[]) => {
      let siblings = roots;
      parts.forEach((name, index) => {
        const path = parts.slice(0, index + 1);
        const existing = siblings.get(name);
        const node = existing || { name, path, children: new Map<string, MutableNode>() };
        siblings.set(name, node);
        siblings = node.children;
      });
    };
    unitFolders.forEach((folder) => addPath(folderPaths.get(folder.id) || [folder.name]));
    unitBlocks.forEach((item) => addPath(pathForBlock(item, folderPaths).slice(0, -1)));
    const serialize = (nodes: Map<string, MutableNode>): DirectoryTreeNode[] => [...nodes.values()]
      .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }))
      .map((node) => ({ name: node.name, path: node.path, children: serialize(node.children) }));
    return serialize(roots);
  }, [folderPaths, unitBlocks, unitFolders]);

  useEffect(() => {
    if (!currentPath.length) return;
    setExpandedFolderPaths((current) => [...new Set([
      ...current,
      ...currentPath.slice(0, -1).map((_, index) => pathKey(currentPath.slice(0, index + 1))),
    ])]);
  }, [currentPath]);

  const searchResults = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return [];
    return unitBlocks.filter((item) => `${item.title} ${item.source_name} ${item.content_preview} ${item.locator}`.toLowerCase().includes(normalized));
  }, [query, unitBlocks]);

  const directoryEntries = useMemo<DirectoryEntry[]>(() => {
    const folders = new Map<string, { count: number; kinds: Set<DataHubBlock['kind']>; customId?: string }>();
    const files: DataHubBlock[] = [];
    unitFolders.forEach((folder) => {
      const parts = folderPaths.get(folder.id) || [folder.name];
      if (!startsWithPath(parts, currentPath)) return;
      const remaining = parts.slice(currentPath.length);
      if (!remaining.length) return;
      const exactFolder = folderByPath.get(pathKey([...currentPath, remaining[0]]));
      const current = folders.get(remaining[0]) || { count: 0, kinds: new Set<DataHubBlock['kind']>(), customId: exactFolder?.id };
      if (remaining.length === 2) current.count += 1;
      current.customId ||= exactFolder?.id;
      folders.set(remaining[0], current);
    });
    unitBlocks.forEach((item) => {
      const parts = pathForBlock(item, folderPaths);
      if (!startsWithPath(parts, currentPath)) return;
      const remaining = parts.slice(currentPath.length);
      if (remaining.length > 1) {
        const exactFolder = folderByPath.get(pathKey([...currentPath, remaining[0]]));
        const current = folders.get(remaining[0]) || { count: 0, kinds: new Set<DataHubBlock['kind']>(), customId: exactFolder?.id };
        if (remaining.length === 2) current.count += 1;
        current.kinds.add(item.kind); folders.set(remaining[0], current);
      } else if (remaining.length === 1) files.push(item);
    });
    const folderEntries: DirectoryEntry[] = [...folders.entries()]
      .map(([name, detail]) => ({ type: 'folder' as const, name, count: detail.count, kinds: detail.kinds, customId: detail.customId }))
      .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }));
    const fileEntries: DirectoryEntry[] = files
      .sort((a, b) => sortMode === 'date'
        ? timestampOf(b.modified_at, b.updated_at) - timestampOf(a.modified_at, a.updated_at) || a.title.localeCompare(b.title, 'zh-CN', { numeric: true })
        : (categoryLabels[a.category || 'other'] || a.category || 'other').localeCompare(categoryLabels[b.category || 'other'] || b.category || 'other', 'zh-CN') || a.title.localeCompare(b.title, 'zh-CN', { numeric: true }))
      .map((item) => ({ type: 'file' as const, block: item }));
    return [...folderEntries, ...fileEntries];
  }, [currentPath, folderByPath, folderPaths, sortMode, unitBlocks, unitFolders]);

  const displayedFiles = query.trim() ? searchResults : directoryEntries.filter((item): item is Extract<DirectoryEntry, { type: 'file' }> => item.type === 'file').map((item) => item.block);
  const displayedSelected = displayedFiles.length > 0 && displayedFiles.every((item) => selectedIds.includes(item.id));
  const selectedBlocks = useMemo(() => selectedIds.map((id) => catalog?.blocks.find((item) => item.id === id)).filter((item): item is DataHubBlock => !!item), [catalog, selectedIds]);
  const currentCustomFolder = folderByPath.get(pathKey(currentPath));
  const canCreateFolder = currentPath.length === 0 || !!currentCustomFolder;

  const sourceRootForFolder = (folderId: string) => {
    const byId = new Map(unitFolders.map((folder) => [folder.id, folder]));
    let current = byId.get(folderId);
    const visited = new Set<string>();
    while (current && !visited.has(current.id)) {
      visited.add(current.id);
      if (current.source_folder_id) return current;
      current = current.parent_id ? byId.get(current.parent_id) : undefined;
    }
    return undefined;
  };

  const canTransferLocally = (blocks: DataHubBlock[], destination: string) => {
    if (!destination || !blocks.length) return false;
    const destinationSource = sourceRootForFolder(destination);
    if (!destinationSource || destinationSource.source_kind !== 'local') return false;
    return blocks.every((item) => item.kind === 'original'
      && item.source_kind === 'local'
      && !!item.source_folder_id
      && item.source_folder_id === destinationSource.source_folder_id);
  };

  const selectUnit = (next: DataHubUnit) => {
    if (next.id === unit?.id) return;
    if (selectedIds.length) setNotice('已切换课程，并清空上一课程的已选资料。');
    setSelectedIds([]);
    setUnit(next); setCurrentPath([]); setBlock(null); setQuery(''); setKindFilter('');
    const summary = catalogSummary.current;
    if (summary) {
      setCatalog(summary);
      void loadUnitCatalog(next, summary);
    }
  };

  const inspectBlock = async (item: DataHubBlock, tab: PreviewTab = 'original') => {
    setBlockLoading(true); setError(''); setPreviewTab(tab); setBlock(item);
    try {
      const detail = await dataHubApi.block(item.id);
      setBlock(detail);
      if (tab === 'original' && !detail.preview_url) setPreviewTab('metadata');
    } catch (reason) { setError(getErrorMessage(reason)); setBlock(null); }
    finally { setBlockLoading(false); }
  };

  const toggleSelection = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const toggleDisplayed = () => setSelectedIds((current) => displayedSelected
    ? current.filter((id) => !displayedFiles.some((item) => item.id === id))
    : [...new Set([...current, ...displayedFiles.map((item) => item.id)])]);
  const openMaterialUnitImport = async (blocks: DataHubBlock[]) => {
    if (!unit) return;
    const importable = blocks.filter((item) => item.kind === 'original' && !!materialIdOf(item));
    if (!importable.length) { setError('请选择课程资料库中的原始文件。'); return; }
    if (importable.length > 40) { setError('单次最多导入 40 个文件，请缩小选择范围。'); return; }
    setError(''); setMaterialUnits([]); setMaterialUnitsLoading(true); setMaterialImportPreviewLoading(true);
    let enriched = importable;
    try {
      enriched = await Promise.all(importable.map(async (item) => {
        try { return await dataHubApi.block(item.id); } catch { return item; }
      }));
    } finally { setMaterialImportPreviewLoading(false); }
    setMaterialImportDialog({
      blocks: enriched, previewId: enriched[0].id, mode: 'create',
      title: enriched.length === 1 ? enriched[0].title.replace(/\.[^.]+$/, '') : `${unit.archive_name}资料单元`,
      targetUnitId: '',
    });
    try {
      const response = await materialUnitApi.list(unit.archive_id);
      setMaterialUnits(response.items);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMaterialUnitsLoading(false); }
  };

  const submitMaterialUnitImport = async () => {
    if (!unit || !materialImportDialog) return;
    const materialIds = materialImportDialog.blocks.map(materialIdOf).filter((id): id is string => !!id);
    if (materialImportDialog.mode === 'create' && !materialImportDialog.title.trim()) { setError('请输入资料单元名称。'); return; }
    if (materialImportDialog.mode === 'append' && !materialImportDialog.targetUnitId) { setError('请选择要追加的资料单元。'); return; }
    setMaterialImporting(true); setError('');
    try {
      if (materialImportDialog.mode === 'create') { const rec = await materialUnitApi.create({ archive_id: unit.archive_id, title: materialImportDialog.title.trim(), material_ids: materialIds }); startedParse(rec.id, materialIds); }
      else { const rec = await materialUnitApi.append(materialImportDialog.targetUnitId, materialIds); startedParse(rec.id, materialIds); }
      setSelectedIds([]); setMaterialImportDialog(null);
      setNotice(`已导入 ${materialIds.length} 个文件，正在后台提取正文…`);
      onMaterialUnitImported();
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMaterialImporting(false); }
  };

  const openCreateFolder = () => {
    if (!unit) return;
    if (!canCreateFolder) {
      setError('当前目录来自原文件路径，请返回主目录或进入可管理文件夹后再新建子文件夹。');
      return;
    }
    setError(''); setItemMenu(null);
    setOrganizeDialog({
      mode: 'create', name: '', parentId: currentCustomFolder?.id || null,
      systemParent: null,
      parentLabel: currentPath.length ? `主目录 / ${currentPath.join(' / ')}` : '主目录',
    });
  };

  const openCreateLibraryRoot = () => {
    setError(''); setItemMenu(null);
    setOrganizeDialog({ mode: 'create-root', name: '' });
  };

  const folderDescendantIds = (folderId: string) => {
    const ids = new Set<string>([folderId]);
    let changed = true;
    while (changed) {
      changed = false;
      unitFolders.forEach((folder) => {
        if (folder.parent_id && ids.has(folder.parent_id) && !ids.has(folder.id)) { ids.add(folder.id); changed = true; }
      });
    }
    return ids;
  };

  const submitOrganize = async () => {
    if (!organizeDialog) return;
    const rootOperation = organizeDialog.mode === 'create-root' || organizeDialog.mode === 'rename-root';
    if (!unit && !rootOperation) return;
    let preferredArchiveId = unit?.archive_id;
    setMutating(true); setError(''); setNotice('');
    try {
      if (organizeDialog.mode === 'create-root') {
        const created = await dataHubApi.createLibraryRoot(organizeDialog.name);
        preferredArchiveId = created.id;
        setCurrentPath([]); setBlock(null); setSelectedIds([]);
        setNotice(`已在资料库根目录创建“${created.name}”。`);
      } else if (organizeDialog.mode === 'rename-root') {
        const renamed = await dataHubApi.renameLibraryRoot(organizeDialog.archiveId, organizeDialog.name);
        preferredArchiveId = renamed.id;
        setNotice(`顶层文件夹已重命名为“${renamed.name}”。`);
      } else if (organizeDialog.mode === 'create') {
        const updated = await dataHubApi.createFolder({ unit_id: unit!.id, name: organizeDialog.name, parent_id: organizeDialog.parentId, system_parent: organizeDialog.systemParent });
        const folderName = organizeDialog.name.trim();
        const created = updated.folders.find((folder) => folder.parent_id === organizeDialog.parentId && folder.name === folderName);
        const localRoot = organizeDialog.parentId ? sourceRootForFolder(organizeDialog.parentId) : undefined;
        if (created && localRoot?.source_kind === 'local') {
          setPendingLocalSyncs((current) => [...current, {
            id: crypto.randomUUID(), kind: 'folder', unitId: unit!.id, archiveId: unit!.archive_id,
            folderId: created.id, label: folderName,
            pathLabel: `${organizeDialog.parentLabel} / ${folderName}`,
          }]);
          setNotice('文件夹已在平台创建，可点击“同步到本地”写入本机目录。');
        } else {
          setNotice(`文件夹已创建于：${organizeDialog.parentLabel} / ${folderName}`);
        }
      } else if (organizeDialog.mode === 'rename-folder') {
        await dataHubApi.updateFolder(organizeDialog.folder.id, { name: organizeDialog.name });
        setNotice('文件夹名称已更新。'); setCurrentPath([]);
      } else if (organizeDialog.mode === 'move-folder') {
        const value = organizeDialog.destination;
        await dataHubApi.updateFolder(organizeDialog.folder.id, {
          move: true,
          parent_id: value.startsWith('folder:') ? value.slice(7) : null,
          system_parent: value.startsWith('system:') ? value.slice(7) as DataHubBlock['kind'] : null,
        });
        setNotice('文件夹已移动。'); setCurrentPath([]);
      } else if (organizeDialog.mode === 'delete-folder') {
        await dataHubApi.deleteFolder(organizeDialog.folder.id, true);
        setNotice('文件夹及其中的平台文件已删除。'); setCurrentPath([]); setBlock(null); setSelectedIds([]);
      } else if (organizeDialog.mode === 'delete-source') {
        if (!organizeDialog.folder.source_folder_id) throw new Error('来源文件夹标识缺失');
        await dataHubApi.deleteSource(unit!.archive_id, organizeDialog.folder.source_folder_id);
        setNotice(`来源文件夹“${organizeDialog.folder.name}”已从平台移除，本机源文件保持不变。`);
        setCurrentPath([]); setBlock(null); setSelectedIds([]);
      } else if (organizeDialog.mode === 'delete-blocks') {
        await dataHubApi.deleteBlocks({ unit_id: unit!.id, block_ids: organizeDialog.blocks.map((item) => item.id) });
        setNotice(`${organizeDialog.blocks.length} 个平台文件已删除。`); setBlock(null); setSelectedIds([]);
      } else if (organizeDialog.mode === 'rename-block') {
        await dataHubApi.updateBlock(organizeDialog.block.id, { unit_id: unit!.id, title: organizeDialog.name });
        setNotice('资料显示名称已更新，原文件名保持不变。');
      } else if (organizeDialog.syncMode === 'platform') {
        await dataHubApi.moveBlocks({ unit_id: unit!.id, block_ids: organizeDialog.blocks.map((item) => item.id), folder_id: organizeDialog.destination || null });
        setNotice(organizeDialog.destination ? `${organizeDialog.blocks.length} 项资料已在平台目录中移动，本机文件保持不变。` : `${organizeDialog.blocks.length} 项资料已恢复到原文件路径。`);
        setSelectedIds([]); setCurrentPath([]);
      } else {
        if (!canTransferLocally(organizeDialog.blocks, organizeDialog.destination)) throw new Error('所选文件与目标文件夹不属于同一本机来源，只能调整平台目录。');
        await dataHubApi.transferLocalMaterials({
          unit_id: unit!.id,
          block_ids: organizeDialog.blocks.map((item) => item.id),
          destination_folder_id: organizeDialog.destination,
          operation: organizeDialog.syncMode,
        });
        setNotice(organizeDialog.syncMode === 'copy'
          ? `已将 ${organizeDialog.blocks.length} 个本机文件复制到目标目录，原文件保持不变。`
          : `已将 ${organizeDialog.blocks.length} 个本机原文件移动到目标目录，并刷新平台索引。`);
        setSelectedIds([]); setCurrentPath([]);
      }
      await refresh(preferredArchiveId); onDataChanged(); setOrganizeDialog(null); setItemMenu(null);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMutating(false); }
  };

  const openMaterialWithSystem = async (item: DataHubBlock) => {
    const materialId = materialIdOf(item);
    if (!item.archive_id || !materialId) return;
    setError('');
    try {
      const result = await dataHubApi.openMaterial(item.archive_id, materialId);
      setNotice(result.message);
    } catch (reason) { setError(getErrorMessage(reason)); }
  };

  const reloadMaterial = async (item: DataHubBlock) => {
    const materialId = materialIdOf(item);
    if (!item.archive_id || !materialId) return;
    setMutating(true); setError('');
    try {
      const result = await dataHubApi.reloadMaterial(item.archive_id, materialId);
      await refresh(item.archive_id); onDataChanged();
      setNotice(result.reloaded ? `“${item.title}”已从本机源文件重新加载。` : `“${item.title}”与平台记录一致，无需更新。`);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setMutating(false); setItemMenu(null); }
  };

  const refreshSourceFolder = async (folder: DataHubFolder) => {
    if (!unit || !folder.source_folder_id) return;
    if (folder.source_kind === 'upload') {
      const selectionKind = folder.source_selection_kind || 'folder';
      setPendingUploadRefresh({ archiveId: unit.archive_id, sourceId: folder.source_folder_id, sourceName: folder.name, selectionKind });
      if (selectionKind === 'files') refreshFileInput.current?.click();
      else {
        try {
          const picked = await pickBrowserDirectory();
          if (picked === undefined) folderInput.current?.click();
          else if (picked) await refreshUploadedSource(picked.files, { archiveId: unit.archive_id, sourceId: folder.source_folder_id, sourceName: folder.name, selectionKind }, picked.directoryPaths);
          else setPendingUploadRefresh(null);
        } catch (reason) { setError(getErrorMessage(reason)); setPendingUploadRefresh(null); }
      }
      return;
    }
    setSourceDiffLoading(true); setError(''); setNotice('');
    try {
      const result = await dataHubApi.sourceDiff(unit.archive_id, folder.source_folder_id);
      setSourceDiff(result);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setSourceDiffLoading(false); }
  };

  const reconcileSource = async (direction: 'update_platform' | 'update_local') => {
    if (!sourceDiff) return;
    setSourceReconciling(direction); setError(''); setNotice('');
    try {
      const result = await dataHubApi.reconcileSource(sourceDiff.archive_id, sourceDiff.source_id, direction);
      await refresh(sourceDiff.archive_id); onDataChanged(); setSourceDiff(null);
      setNotice(result.message);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setSourceReconciling(null); }
  };

  const refreshUploadedSource = async (files: File[], source: { archiveId: string; sourceId: string; sourceName: string; selectionKind: 'files' | 'folder' }, directoryPaths: string[] = []) => {
    setSyncing(true); setError('');
    try {
      const itemCount = Math.max(1, files.length + directoryPaths.length);
      setSourceUploadProgress({ done: 0, total: itemCount });
      const result = await onImportFolder(files, source.archiveId, source.sourceId, source.sourceName, (done, total) => setSourceUploadProgress({ done, total }), directoryPaths);
      if (!result) return;
      await refresh(source.archiveId); onDataChanged();
      setNotice(`“${source.sourceName}”已根据重新选择的${source.selectionKind === 'files' ? '原文件' : '原文件夹'}更新。`);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setSyncing(false); setPendingUploadRefresh(null); setSourceUploadProgress({ done: 0, total: 0 }); }
  };

  const openSourceFolder = async (folder: DataHubFolder) => {
    if (!unit || !folder.source_folder_id) return;
    setError('');
    try {
      const result = await dataHubApi.openSource(unit.archive_id, folder.source_folder_id);
      setNotice(result.message);
    } catch (reason) { setError(getErrorMessage(reason)); }
  };

  const ensureCurrentImportFolder = async () => {
    if (!unit) return null;
    if (currentCustomFolder) return currentCustomFolder.id;
    if (!currentPath.length) return null;
    let parentId = mountedSourceRoot?.id || null;
    const prefix: string[] = [];
    for (const part of currentPath) {
      prefix.push(part);
      const existing = folderByPath.get(pathKey(prefix));
      if (existing) {
        parentId = existing.id;
        continue;
      }
      const updated = await dataHubApi.createFolder({
        unit_id: unit.id, name: part, parent_id: parentId, system_parent: null,
      });
      const created = updated.folders.find((folder) => folder.parent_id === parentId && folder.name === part);
      if (!created) throw new Error(`无法建立当前目录：${part}`);
      parentId = created.id;
    }
    return parentId;
  };

  const indexBrowserSelection = async (files: File[], directoryPaths: string[] = [], selectedRootName = '') => {
    if (!files.length && !selectedRootName) return;
    setSyncing(true); setError(''); setNotice('');
    try {
      const folderRoot = selectedRootName || files[0]?.webkitRelativePath.split('/')[0] || '';
      const sourceName = folderRoot || (files.length === 1 ? `单文件 · ${files[0].name}` : `文件导入 · ${new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date())}`);
      const itemCount = Math.max(1, files.length + directoryPaths.length);
      setSourceUploadProgress({ done: 0, total: itemCount });
      const destinationFolderId = await ensureCurrentImportFolder();
      const result = await onImportFolder(files, unit?.archive_id || null, null, sourceName, (done, total) => setSourceUploadProgress({ done, total }), directoryPaths, destinationFolderId);
      if (!result) return;
      await refresh(result.archiveId); onDataChanged();
      const destinationLabel = currentPath.length ? `主目录 / ${currentPath.join(' / ')}` : '主目录';
      const destinationSource = destinationFolderId ? sourceRootForFolder(destinationFolderId) : mountedSourceRoot || undefined;
      if (destinationFolderId && destinationSource?.source_kind === 'local') {
        const isFolderSelection = !!selectedRootName || directoryPaths.length > 0 || files.some((file) => !!file.webkitRelativePath);
        setPendingLocalSyncs((current) => [...current, {
          id: crypto.randomUUID(), kind: 'upload', unitId: unit!.id, archiveId: result.archiveId,
          folderId: destinationFolderId, browserSourceId: result.sourceId,
          rootName: isFolderSelection ? folderRoot : '', files, directoryPaths,
          label: sourceName, pathLabel: isFolderSelection && folderRoot ? `${destinationLabel} / ${folderRoot}` : destinationLabel,
        }]);
        setNotice('索引已建立，可点击“同步到本地”传输文件内容。');
      } else {
        setNotice(`已导入到 ${destinationLabel}：${files.length} 个文件、${directoryPaths.length} 个子文件夹；文件正文仍按需导入。`);
      }
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setSyncing(false); setSourceUploadProgress({ done: 0, total: 0 }); }
  };

  const executePendingLocalSyncs = async () => {
    if (!pendingLocalSyncs.length) return;
    const queue = [...pendingLocalSyncs];
    let completed = 0;
    let preferredArchiveId = unit?.archive_id;
    setLocalSyncing(true); setError(''); setNotice('');
    try {
      for (const item of queue) {
        if (item.kind === 'folder') {
          await dataHubApi.syncFolderToLocal({ unit_id: item.unitId, folder_id: item.folderId });
        } else {
          await dataHubApi.syncUploadsToLocal({
            unit_id: item.unitId,
            folder_id: item.folderId,
            browser_source_id: item.browserSourceId,
            root_name: item.rootName,
            directories: item.directoryPaths,
            files: item.files,
          });
        }
        completed += 1;
        preferredArchiveId = item.archiveId;
        setPendingLocalSyncs((current) => current.filter((change) => change.id !== item.id));
      }
      await refresh(preferredArchiveId); onDataChanged(); setLocalSyncOpen(false);
      setNotice(`已将 ${completed} 项变更同步到本地。`);
    } catch (reason) {
      setError(`${completed ? `已完成 ${completed} 项；` : ''}${getErrorMessage(reason)}。未完成项已保留，可处理后重试。`);
    } finally {
      setLocalSyncing(false);
    }
  };

  const openBrowserDirectoryImport = async () => {
    setError(''); setNotice('');
    try {
      // 优先: 后端系统文件夹选择器 → 拿本机绝对路径 → 自动关联为本地来源(可系统打开+刷新同步)
      // 后端不可用/取消时回退到浏览器选择 (showDirectoryPicker)
      try {
        const pickedResponse = await fetch('/api/data-hub/pick-folder', { method: 'POST' });
        const pickedJson = await pickedResponse.json();
        if (pickedJson && pickedJson.canceled === false && pickedJson.path) {
          const rootPath = pickedJson.path;
          const targetArchive = unit?.archive_id;
          if (targetArchive) {
            setSyncing(true);
            const result = await dataHubApi.scanLocal({
              root_path: rootPath,
              archive_id: targetArchive,
              source_name: rootPath.split(/[\\/]/).filter(Boolean).pop() || '本地资料',
            });
            setNotice(`已关联本地文件夹（${result.total_files || 0} 份资料），双击文件可用系统默认程序打开。`);
            await refresh(); onDataChanged();
            setSyncing(false);
            return;
          }
        }
      } catch (pickerErr) {
        // 后端选择器不可用 → 走浏览器选择器回退
      }
      const picked = await pickBrowserDirectory();
      if (picked === undefined) directoryUploadInput.current?.click();
      else if (picked) await indexBrowserSelection(picked.files, picked.directoryPaths, picked.rootName);
    } catch (reason) { setError(getErrorMessage(reason)); setSyncing(false); }
  };

  const inspectArchiveDeletion = async (archiveId: string) => {
    const archive = archives.find((item) => item.id === archiveId);
    if (!archive) return;
    setError(''); setNotice('');
    setArchiveDelete({ archive, impact: null }); setArchiveDeleteLoading(true);
    try {
      const impact = await courseArchiveApi.deletionImpact(archiveId);
      setArchiveDelete((current) => current?.archive.id === archiveId ? { ...current, impact } : current);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setArchiveDeleteLoading(false); }
  };

  const confirmArchiveDeletion = async () => {
    if (!archiveDelete?.impact) return;
    setArchiveDeleting(true); setError('');
    const title = archiveDelete.archive.name;
    try {
      const result = await onDeleteArchive(archiveDelete.archive.id);
      if (!result) { setError('课程删除失败，请稍后重试。'); return; }
      setArchiveDelete(null); setCurrentPath([]); setBlock(null); setSelectedIds([]);
      await refresh();
      setNotice(`资料库文件夹“${title}”及其平台关联数据已删除，本机源目录保持不变。`);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setArchiveDeleting(false); }
  };

  const unavailableMoveFolderIds = organizeDialog?.mode === 'move-folder'
    ? folderDescendantIds(organizeDialog.folder.id)
    : new Set<string>();

  const renderFileRow = (item: DataHubBlock) => <FileRow
    key={item.id} item={item} selected={selectedIds.includes(item.id)} focused={block?.id === item.id}
    canSystemOpen={item.source_kind === 'local' || !!item.original_url}
    menuOpen={itemMenu?.type === 'block' && itemMenu.id === item.id}
    onToggle={() => toggleSelection(item.id)} onSystemOpen={() => item.source_kind === 'local' || item.original_url ? void openMaterialWithSystem(item) : void inspectBlock(item, 'metadata')}
    onInspect={() => { setItemMenu(null); void inspectBlock(item, item.preview_url ? 'original' : 'metadata'); }}
    onReload={() => void reloadMaterial(item)}
    onMenu={() => setItemMenu((current) => current?.type === 'block' && current.id === item.id ? null : { type: 'block', id: item.id })}
    onRename={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: 'rename-block', name: item.title, block: item }); }}
    onMove={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: 'move-blocks', destination: item.folder_id || '', blocks: [item], syncMode: 'platform' }); }}
    onDelete={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: 'delete-blocks', blocks: [item] }); }}
  />;

  const renderFolderTree = (nodes: DirectoryTreeNode[], depth = 0) => nodes.map((node) => {
    const key = pathKey(node.path);
    const expanded = expandedFolderPaths.includes(key);
    const selected = pathKey(currentPath) === key;
    return <div className="tree-folder-node" key={key}>
      <div className={`tree-folder-row ${selected ? 'active' : ''}`} style={{ paddingLeft: `${depth * 12}px` }}>
        {node.children.length > 0 ? <button type="button" className="tree-folder-toggle" onClick={() => setExpandedFolderPaths((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key])} aria-label={`${expanded ? '收起' : '展开'}文件夹${node.name}`} title={expanded ? '收起' : '展开'}>{expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</button> : <span className="tree-folder-spacer" />}
        <button type="button" className="tree-folder-link" title={`主目录 / ${node.path.join(' / ')}`} onClick={() => { setCurrentPath(node.path); if (node.children.length > 0 && !expanded) setExpandedFolderPaths((current) => [...current, key]); }}>{selected || expanded ? <FolderOpen size={13} /> : <Folder size={13} />}<span>{node.name}</span></button>
      </div>
      {expanded && node.children.length > 0 && <div>{renderFolderTree(node.children, depth + 1)}</div>}
    </div>;
  });

  if (loading && !catalog) return <main className="hub-empty"><Loader2 className="spin" /><strong>正在读取资料库目录…</strong></main>;
  return (
    <main className={`hub-workspace ${selectedBlocks.length ? 'has-selection' : ''} ${block ? 'has-inspector' : ''}`}>
      <header className="hub-header">
        <div><span>数据中台</span><h1>课程资料库</h1><p>{unit ? `资料库 / ${unit.archive_name}` : '从左侧选择或新建顶层文件夹'}</p></div>
        <div><button type="button" className="secondary-button" onClick={() => void refresh()} title="刷新页面中的资料索引"><RefreshCw size={15} />刷新页面</button></div>
      </header>

      <section className="hub-summary-row" aria-label="资料概览">
        <div className="hub-stats">
          <span><Database size={14} /><strong>{catalog?.stats.courses || 0}</strong> 顶层文件夹</span>
          <span><Archive size={14} /><strong>{catalog?.stats.materials || 0}</strong> 原始文件</span>
        </div>
        <div className="hub-toolbar">
          <div className="hub-searchbox"><Search size={15} aria-hidden="true" /><input name="hub-search" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索当前文件夹…" aria-label="搜索当前资料库文件夹" />{query && <button type="button" onClick={() => setQuery('')} aria-label="清除搜索" title="清除搜索"><X size={13} /></button>}</div>
          <button type="button" className={filtersOpen || kindFilter ? 'active' : ''} onClick={() => setFiltersOpen((value) => !value)} aria-expanded={filtersOpen}><ListFilter size={14} />{kindFilter ? kindLabels[kindFilter] : '筛选'}{kindFilter && <i>1</i>}</button>
        </div>
        {filtersOpen && <div className="hub-filter-popover"><strong>内容类型</strong><button type="button" className={!kindFilter ? 'active' : ''} onClick={() => { setKindFilter(''); setCurrentPath([]); setFiltersOpen(false); }}>全部</button>{fileKindOrder.map((kind) => <button type="button" key={kind} className={kindFilter === kind ? 'active' : ''} onClick={() => { setKindFilter(kind); setCurrentPath([]); setFiltersOpen(false); }}>{kindLabels[kind]}</button>)}</div>}
      </section>

      {(notice || error) && <div className={`hub-notice ${error ? 'error' : ''}`} aria-live="polite">{error ? <X size={14} /> : <CheckCircle2 size={14} />}{error || notice}<button type="button" onClick={() => { setNotice(''); setError(''); }} aria-label="关闭提示"><X size={13} /></button></div>}
      {syncing && sourceUploadProgress.total > 0 && <div className="source-upload-progress hub-index-progress" role="status"><span><strong>正在建立资料索引</strong><small>{sourceUploadProgress.done} / {sourceUploadProgress.total} 项</small></span><progress max={sourceUploadProgress.total} value={sourceUploadProgress.done} /></div>}

      <div className="hub-browser">
        <aside className="hub-tree">
          <header><span>资料库目录</span><div><em>{catalog?.stats.courses || 0}</em><button type="button" onClick={openCreateLibraryRoot} aria-label="新建顶层文件夹" title="在资料库根目录新建文件夹"><FolderPlus size={14} /></button></div></header>
          <div className="hub-tree-scroll">
            {libraryRoots.map(({ unit: rootUnit, archive }) => {
              const selected = unit?.archive_id === rootUnit.archive_id;
              return <section key={rootUnit.archive_id}>
                <div className="tree-library-row">
                  <button type="button" className={`tree-library ${selected ? 'active' : ''}`} aria-current={selected ? 'page' : undefined} onClick={() => selectUnit(rootUnit)}>{selected ? <FolderOpen size={15} /> : <Folder size={15} />}<span title={rootUnit.archive_name}>{rootUnit.archive_name}</span><small>{archive?.total_files ?? rootUnit.material_count} 项</small></button>
                  <div className="tree-library-actions"><button type="button" onClick={() => { setError(''); setOrganizeDialog({ mode: 'rename-root', name: rootUnit.archive_name, currentName: rootUnit.archive_name, archiveId: rootUnit.archive_id }); }} aria-label={`重命名顶层文件夹${rootUnit.archive_name}`} title="重命名顶层文件夹"><Pencil size={12} /></button><button type="button" onClick={() => void inspectArchiveDeletion(rootUnit.archive_id)} aria-label={`删除顶层文件夹${rootUnit.archive_name}`} title="删除顶层文件夹"><Trash2 size={13} /></button></div>
                </div>
                {selected && <div className="tree-directory">{unitLoading ? <div className="tree-directory-loading"><Loader2 className="spin" size={12} />读取目录…</div> : folderNavigationTree.length > 0 ? renderFolderTree(folderNavigationTree) : <div className="tree-directory-loading">当前文件夹为空</div>}</div>}
              </section>;
            })}
            {!libraryRoots.length && <div className="tree-library-empty"><Folder size={20} /><span>资料库根目录为空</span><button type="button" onClick={openCreateLibraryRoot}><FolderPlus size={13} />新建顶层文件夹</button></div>}
          </div>
          {unit && <button type="button" className="tree-manage" onClick={() => onOpenArchive(unit.archive_id)}><FileSearch size={14} />整理与分析当前资料<ChevronRight size={13} /></button>}
        </aside>

        <section className="hub-directory">
          <header className="directory-header">
            <nav aria-label="当前资料路径"><Home size={14} /><span className="directory-root-label">资料库</span>{unit && <><ChevronRight size={12} /><button type="button" title={unit.archive_name} onClick={() => setCurrentPath([])}>{unit.archive_name}</button>{currentPath.map((part, index) => <span key={`${part}-${index}`}><ChevronRight size={12} /><button type="button" title={part} onClick={() => setCurrentPath(currentPath.slice(0, index + 1))}>{part}</button></span>)}</>}</nav>
            <div><button type="button" onClick={openCreateFolder} disabled={!unit || unitLoading || !canCreateFolder} title={canCreateFolder ? '在当前位置新建子文件夹' : '请先选择顶层文件夹或进入可管理目录'}><FolderPlus size={13} />新建子文件夹</button><button type="button" disabled={!unit || syncing || unitLoading} onClick={() => fileUploadInput.current?.click()} title="选择文件并建立一级索引"><Upload size={13} />导入文件</button><button type="button" disabled={!unit || syncing || unitLoading} onClick={() => void openBrowserDirectoryImport()} title="选择文件夹并保留其中的空目录"><FolderOpen size={13} />导入文件夹</button><details className="hub-toolbar-more"><summary>更多</summary><button type="button" className={`local-sync-button ${pendingLocalSyncs.length ? 'pending' : ''}`} disabled={!pendingLocalSyncs.length || localSyncing} onClick={() => { setError(''); setLocalSyncOpen(true); }} title={pendingLocalSyncs.length ? `查看并同步 ${pendingLocalSyncs.length} 项本次变更` : '本次会话暂无可同步变更'}><FolderSync size={13} />同步到本地{pendingLocalSyncs.length > 0 && <i>{pendingLocalSyncs.length}</i>}</button>{mountedSourceRoot && <button type="button" disabled={syncing || unitLoading || sourceDiffLoading} onClick={() => void refreshSourceFolder(mountedSourceRoot)} title="比较本地目录与平台记录，再选择同步方向">{sourceDiffLoading ? <Loader2 className="spin" size={13} /> : <RotateCw size={13} />}{sourceDiffLoading ? '正在比较…' : '刷新与同步'}</button>}{mountedSourceRoot?.source_kind === 'local' && <button type="button" onClick={() => void openSourceFolder(mountedSourceRoot)} title="在系统文件管理器中打开来源文件夹"><ExternalLink size={13} />系统打开</button>}<nav className="directory-sort" aria-label="文件排序方式"><button type="button" className={sortMode === 'category' ? 'active' : ''} aria-pressed={sortMode === 'category'} onClick={() => setSortMode('category')} title="按资料类别排序"><Tags size={12} />类别</button><button type="button" className={sortMode === 'date' ? 'active' : ''} aria-pressed={sortMode === 'date'} onClick={() => setSortMode('date')} title="按修改日期排序"><CalendarDays size={12} />日期</button></nav></details><small>{unitLoading ? '正在读取当前目录…' : syncing ? '正在建立索引…' : query.trim() ? `找到 ${searchResults.length} 项` : unit ? `已载入 ${unitBlocks.length}/${unit.material_count || 0} 份 · 当前目录 ${directoryEntries.length} 项` : '请选择顶层文件夹'}</small>{displayedFiles.length > 0 && !unitLoading && <button type="button" onClick={toggleDisplayed} aria-label={displayedSelected ? `取消选择当前文件 ${displayedFiles.length} 项` : `选择当前文件 ${displayedFiles.length} 项`}>{displayedSelected ? <Check size={13} /> : <Square size={13} />}{displayedSelected ? '取消全选' : '选择本页'}</button>}</div>
          </header>

          {unitLoading ? (
            <div className="hub-directory-loading" role="status"><Loader2 className="spin" size={20} /><strong>正在读取当前资料文件夹</strong><span>顶层目录已就绪，文件索引正在按需加载…</span></div>
          ) : query.trim() ? (
            <div className="directory-search-results">
              <header><Search size={14} /><strong>“{query.trim()}”</strong><span>仅显示当前课程匹配结果</span><button type="button" onClick={() => setQuery('')}>返回目录</button></header>
              {searchResults.length > 0 ? <div className="directory-file-list" role="list">{searchResults.map(renderFileRow)}</div> : <div className="hub-no-results"><Search size={24} /><strong>没有匹配资料</strong><span>尝试缩短关键词或清除当前类型筛选。</span><button type="button" onClick={() => { setQuery(''); setKindFilter(''); }}>清除搜索与筛选</button></div>}
            </div>
          ) : directoryEntries.length === 0 ? (
            <div className="hub-no-results"><FolderOpen size={24} /><strong>{unit ? '当前目录为空' : '资料库根目录为空'}</strong><span>{unit ? '可以在当前位置建立子文件夹，或直接导入文件与文件夹。' : '先新建一个顶层文件夹，再在其中整理资料。'}</span>{unit ? <div className="hub-empty-actions">{canCreateFolder && <button type="button" onClick={openCreateFolder}><FolderPlus size={13} />新建子文件夹</button>}<button type="button" disabled={syncing} onClick={() => fileUploadInput.current?.click()}><Upload size={13} />导入文件</button><button type="button" disabled={syncing} onClick={() => void openBrowserDirectoryImport()}><FolderOpen size={13} />导入文件夹</button>{pendingLocalSyncs.length > 0 && <button type="button" className="local-sync-button pending" disabled={localSyncing} onClick={() => { setError(''); setLocalSyncOpen(true); }}><FolderSync size={13} />同步到本地<i>{pendingLocalSyncs.length}</i></button>}{currentPath.length > 0 && <button type="button" onClick={() => setCurrentPath(currentPath.slice(0, -1))}>返回上一级</button>}{kindFilter && <button type="button" onClick={() => setKindFilter('')}>清除类型筛选</button>}</div> : <button type="button" onClick={openCreateLibraryRoot}><FolderPlus size={13} />新建顶层文件夹</button>}</div>
          ) : (
            <div className="directory-content">
              {directoryEntries.some((entry) => entry.type === 'folder') && <section className="directory-folders"><header><span>文件夹</span><small>{directoryEntries.filter((entry) => entry.type === 'folder').length}</small></header><div>{directoryEntries.filter((entry): entry is Extract<DirectoryEntry, { type: 'folder' }> => entry.type === 'folder').map((entry) => {
                const customFolder = entry.customId ? unitFolders.find((item) => item.id === entry.customId) : undefined;
                const menuOpen = !!customFolder && itemMenu?.type === 'folder' && itemMenu.id === customFolder.id;
                const isSource = !!customFolder?.source_folder_id;
                return <div className={`directory-folder-card ${customFolder ? 'custom' : 'system'} ${isSource ? 'source-folder' : ''}`} key={`${entry.customId || 'system'}:${entry.name}`}>
                  <button type="button" className="folder-open-button" title={entry.name} onClick={() => { setItemMenu(null); setCurrentPath([...currentPath, entry.name]); }}><Folder size={21} /><span><strong>{entry.name}</strong><small>{isSource ? `${customFolder?.source_kind === 'local' ? '本地关联' : '浏览器索引'} · ${entry.count} 项` : entry.count ? `${entry.count} 项内容` : customFolder ? '空文件夹' : '0 项内容'}</small></span><ChevronRight size={14} /></button>
                  {customFolder && <div className="folder-actions">{isSource && <button type="button" className="folder-more-button" disabled={syncing} onClick={() => void refreshSourceFolder(customFolder)} aria-label={`刷新来源${entry.name}`} title={customFolder.source_kind === 'local' ? '根据本机路径刷新' : customFolder.source_selection_kind === 'files' ? '重新选择原文件更新索引' : '重新选择原文件夹更新索引'}><RotateCw className={syncing ? 'spin' : ''} size={14} /></button>}{isSource && customFolder.source_kind === 'local' && <button type="button" className="folder-more-button" onClick={() => void openSourceFolder(customFolder)} aria-label={`在系统中打开文件夹${entry.name}`} title="在系统文件管理器中打开"><ExternalLink size={14} /></button>}<button type="button" className="folder-more-button" onClick={() => setItemMenu(menuOpen ? null : { type: 'folder', id: customFolder.id })} aria-label={`管理文件夹${entry.name}`} aria-expanded={menuOpen} title="更多操作"><MoreHorizontal size={15} /></button><button type="button" className="folder-delete-button" onClick={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: isSource ? 'delete-source' : 'delete-folder', folder: customFolder }); }} aria-label={`删除文件夹${entry.name}`} title={isSource ? '从平台移除来源文件夹' : '删除文件夹'}><Trash2 size={14} /></button></div>}
                  {menuOpen && customFolder && <div className="hub-item-menu">{isSource ? <><button type="button" onClick={() => void refreshSourceFolder(customFolder)}><RotateCw size={13} />刷新来源</button>{customFolder.source_kind === 'local' && <button type="button" onClick={() => void openSourceFolder(customFolder)}><ExternalLink size={13} />系统打开</button>}<button type="button" className="danger" onClick={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: 'delete-source', folder: customFolder }); }}><Trash2 size={13} />从平台移除</button></> : <><button type="button" onClick={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: 'rename-folder', name: customFolder.name, folder: customFolder }); }}><Pencil size={13} />重命名</button><button type="button" onClick={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: 'move-folder', destination: '', folder: customFolder }); }}><Move size={13} />移动到</button><button type="button" className="danger" onClick={() => { setItemMenu(null); setError(''); setOrganizeDialog({ mode: 'delete-folder', folder: customFolder }); }}><Trash2 size={13} />删除文件夹</button></>}</div>}
                </div>;
              })}</div></section>}
              {displayedFiles.length > 0 && <section className="directory-files"><header><span>文件</span><small>{displayedFiles.length}</small></header><div className="directory-file-list" role="list">{displayedFiles.map(renderFileRow)}</div></section>}
            </div>
          )}
        </section>

        {(block || blockLoading) && <aside className="hub-inspector" aria-label="文件详情">
          {blockLoading && !block ? <div className="hub-inspector-empty"><Loader2 className="spin" />正在读取完整内容…</div> : block && <>
            <header><div><span className={`hub-kind kind-${block.kind}`}>{kindLabels[block.kind]}</span><h3>{block.title}</h3><small title={block.locator}>{block.source_name || block.locator}</small></div><button type="button" onClick={() => setBlock(null)} aria-label="关闭文件详情"><X size={16} /></button></header>
            <nav className="hub-preview-tabs" aria-label="预览内容" role="tablist"><button type="button" role="tab" aria-selected={previewTab === 'original'} className={previewTab === 'original' ? 'active' : ''} disabled={!block.preview_url} onClick={() => setPreviewTab('original')}>原页预览</button><button type="button" role="tab" aria-selected={previewTab === 'metadata'} className={previewTab === 'metadata' ? 'active' : ''} onClick={() => setPreviewTab('metadata')}>文件信息</button></nav>
            <div className="hub-preview-body">{parseTask && parseTask.status !== 'completed' && parseTask.status !== 'failed' && <div className="hub-parse-progress" style={{ padding: '8px 0', fontSize: 12, color: 'var(--dsw-alias-label-secondary, #bbb)' }}><strong>后台解析中… {Math.round(parseTask.progress)}%</strong><progress value={parseTask.progress} max={100} style={{ width: '100%', marginTop: 4 }} />{(parseTask.materials || []).map(m => <div key={m.id} style={{ fontSize: 11, opacity: .8 }}>{m.name} — {m.status === 'parsed' ? '已提取' : m.status === 'cached' ? '已缓存' : m.status === 'failed' ? '失败' : '解析中 ' + Math.round(m.progress) + '%'}</div>)}</div>}{previewTab === 'original' && block.preview_url ? <iframe title={`${block.title} 原页预览`} src={block.preview_url} /> : <dl><div><dt>文件类型</dt><dd>{extensionOf(block.title)}</dd></div><div><dt>原文件名</dt><dd>{block.source_name || '未记录'}</dd></div><div><dt>目录位置</dt><dd>{block.locator || '未记录'}</dd></div><div><dt>原页预览</dt><dd>{block.preview_url ? '可在当前页面预览' : '该格式请打开原文件查看'}</dd></div><div><dt>正文提取</dt><dd>{block.parse_status === 'parsed' ? '已提取（' + (block.extraction_engine || '解析引擎') + '）' : block.parse_status === 'parse_failed' ? '提取失败' : block.parse_status === 'unsupported' ? '格式不支持提取' : '未提取；进入备课时按需提取'}</dd></div>{block.text ? <div><dt>原文预览</dt><dd><button type="button" onClick={() => window.open('data:text/plain;charset=utf-8,' + encodeURIComponent(block.text!.slice(0, 8000)), '_blank', 'noopener,noreferrer')}><ExternalLink size={13} />查看已提取正文</button></dd></div> : null}<div><dt>更新时间</dt><dd>{formatDate(block.updated_at)}</dd></div></dl>}</div>
            <footer>{block.preview_url && <button type="button" onClick={() => window.open(block.preview_url!, '_blank', 'noopener,noreferrer')}><ExternalLink size={14} />新窗口预览</button>}{block.original_url && <button type="button" onClick={() => window.open(block.original_url!, '_blank', 'noopener,noreferrer')}><Archive size={14} />打开原文件</button>}<button type="button" onClick={() => void openMaterialUnitImport([block])}><PackagePlus size={14} />导入资料单元</button></footer>
          </>}
        </aside>}
      </div>

      {selectedBlocks.length > 0 && <section className="hub-selection-bar" aria-label="已选资料">
        <div><span><CheckCircle2 size={16} /><strong>已选 {selectedBlocks.length} 项</strong></span><small>{selectedBlocks.slice(0, 3).map((item) => item.title).join('、')}{selectedBlocks.length > 3 ? ` 等 ${selectedBlocks.length} 项` : ''}</small></div>
        {selectedBlocks.length > 40 && <em>建议不超过 40 项</em>}
        <button type="button" onClick={() => { setError(''); setOrganizeDialog({ mode: 'move-blocks', destination: '', blocks: selectedBlocks, syncMode: 'platform' }); }}><Move size={13} />移动</button>
        <button type="button" onClick={() => { setError(''); setOrganizeDialog({ mode: 'delete-blocks', blocks: selectedBlocks }); }}><Trash2 size={13} />删除</button>
        <button type="button" onClick={() => setSelectedIds([])}>清空</button>
        <button type="button" className="hub-unit-import-button" onClick={() => void openMaterialUnitImport(selectedBlocks)}><PackagePlus size={14} />导入资料单元</button>
      </section>}

      {materialImportDialog && <div className="hub-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !materialImporting) setMaterialImportDialog(null); }}><section ref={materialImportDialogElement} className="hub-dialog material-import-dialog" role="dialog" aria-modal="true" aria-labelledby="material-import-title">
        <header><div><PackagePlus size={19} /><span><strong id="material-import-title">导入资料单元</strong><small>{materialImportDialog.blocks.length} 个文件 · 导入时按需提取并保存分析</small></span></div><button type="button" disabled={materialImporting} onClick={() => setMaterialImportDialog(null)} aria-label="关闭导入资料单元"><X size={17} /></button></header>
        <div className="material-import-layout">
          <section className="material-import-selection"><header><strong>已选文件</strong><span>{materialImportDialog.blocks.length}</span></header><div>{materialImportDialog.blocks.map((item) => <div key={item.id} className={materialImportDialog.previewId === item.id ? 'active' : ''}><button type="button" onClick={() => setMaterialImportDialog({ ...materialImportDialog, previewId: item.id })}><File size={15} /><span><strong>{item.title}</strong><small>{item.locator}</small></span></button>{materialImportDialog.blocks.length > 1 && <button type="button" disabled={materialImporting} aria-label={`移除${item.title}`} onClick={() => { const remaining = materialImportDialog.blocks.filter((blockItem) => blockItem.id !== item.id); setMaterialImportDialog({ ...materialImportDialog, blocks: remaining, previewId: materialImportDialog.previewId === item.id ? remaining[0].id : materialImportDialog.previewId }); }}><X size={13} /></button>}</div>)}</div></section>
          <section className="material-import-preview">{(() => { const preview = materialImportDialog.blocks.find((item) => item.id === materialImportDialog.previewId) || materialImportDialog.blocks[0]; return <><header><span><strong>{preview.title}</strong><small>{materialImportPreviewLoading ? '正在读取原页预览…' : '导入前原页预览'}</small></span>{preview.preview_url && <button type="button" onClick={() => window.open(preview.preview_url!, '_blank', 'noopener,noreferrer')}><ExternalLink size={14} />新窗口</button>}</header>{materialImportPreviewLoading ? <div className="material-import-no-preview"><Loader2 className="spin" size={25} /><strong>正在准备文件预览</strong><span>只读取原页地址，不会提前提取正文</span></div> : preview.preview_url ? <iframe title={`${preview.title} 导入预览`} src={preview.preview_url} /> : <div className="material-import-no-preview"><FileSearch size={25} /><strong>该格式暂不支持页内预览</strong><span>{preview.locator}</span></div>}</>; })()}</section>
        </div>
        <section className="material-import-target"><div className="material-import-mode" role="radiogroup" aria-label="资料单元导入方式"><button type="button" role="radio" aria-checked={materialImportDialog.mode === 'create'} className={materialImportDialog.mode === 'create' ? 'active' : ''} disabled={materialImporting} onClick={() => setMaterialImportDialog({ ...materialImportDialog, mode: 'create' })}>新建资料单元</button><button type="button" role="radio" aria-checked={materialImportDialog.mode === 'append'} className={materialImportDialog.mode === 'append' ? 'active' : ''} disabled={materialImporting || materialUnitsLoading || !materialUnits.length} onClick={() => setMaterialImportDialog({ ...materialImportDialog, mode: 'append', targetUnitId: materialImportDialog.targetUnitId || materialUnits[0]?.id || '' })}>{materialUnitsLoading ? '读取已有单元…' : `追加到已有单元${materialUnits.length ? `（${materialUnits.length}）` : ''}`}</button></div>{materialImportDialog.mode === 'create' ? <label>资料单元名称<input name="material-unit-title" value={materialImportDialog.title} disabled={materialImporting} onChange={(event) => setMaterialImportDialog({ ...materialImportDialog, title: event.target.value })} /></label> : <label>目标资料单元<select name="material-unit-target" value={materialImportDialog.targetUnitId} disabled={materialImporting} onChange={(event) => setMaterialImportDialog({ ...materialImportDialog, targetUnitId: event.target.value })}><option value="">请选择资料单元</option>{materialUnits.map((item) => <option key={item.id} value={item.id}>{item.title}（{item.material_count} 个文件）</option>)}</select></label>}</section>
        {materialImporting && <div className="material-import-progress" role="status"><Loader2 className="spin" size={18} /><span><strong>正在提取正文并形成初步分析</strong><small>已等待 {materialImportElapsed} 秒。完成后摘要、知识点和解析质量会持久保存，重复导入将复用已有结果。</small></span><progress /></div>}
        {error && <div className="hub-dialog-error" role="alert"><AlertCircle size={14} /><span>{error}</span></div>}
        <footer><button type="button" className="secondary-button" disabled={materialImporting} onClick={() => setMaterialImportDialog(null)}>取消</button><button type="button" className="hub-connect-button" disabled={materialImporting || (materialImportDialog.mode === 'create' ? !materialImportDialog.title.trim() : !materialImportDialog.targetUnitId)} onClick={() => void submitMaterialUnitImport()}>{materialImporting ? <Loader2 className="spin" size={15} /> : <PackagePlus size={15} />}{materialImporting ? '正在导入…' : materialImportDialog.blocks.length === 1 ? '导入当前文件' : `一键导入 ${materialImportDialog.blocks.length} 个文件`}</button></footer>
      </section></div>}

      <input ref={fileUploadInput} className="visually-hidden" type="file" multiple onChange={(event) => { const files = Array.from(event.target.files || []); if (files.length) void indexBrowserSelection(files); event.target.value = ''; }} />
      <input ref={(node) => { directoryUploadInput.current = node; node?.setAttribute('webkitdirectory', ''); }} className="visually-hidden" type="file" multiple onChange={(event) => { const files = Array.from(event.target.files || []); if (files.length) void indexBrowserSelection(files); event.target.value = ''; }} />
      <input ref={refreshFileInput} className="visually-hidden" type="file" multiple onChange={(event) => { const files = Array.from(event.target.files || []); if (files.length && pendingUploadRefresh?.selectionKind === 'files') void refreshUploadedSource(files, pendingUploadRefresh); event.target.value = ''; }} />
      <input ref={(node) => { folderInput.current = node; node?.setAttribute('webkitdirectory', ''); }} className="visually-hidden" type="file" multiple onChange={(event) => { const files = Array.from(event.target.files || []); if (files.length && pendingUploadRefresh) void refreshUploadedSource(files, pendingUploadRefresh); event.target.value = ''; }} />
      {archiveDelete && <div className="hub-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !archiveDeleting) setArchiveDelete(null); }}><section ref={archiveDeleteDialogElement} className="hub-dialog hub-archive-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="hub-archive-delete-title">
        <header><div><Trash2 size={18} /><span><strong id="hub-archive-delete-title">删除顶层文件夹</strong><small>平台目录记录及其关联数据将一并移除</small></span></div><button type="button" disabled={archiveDeleting} onClick={() => setArchiveDelete(null)} aria-label="关闭删除确认"><X size={17} /></button></header>
        <div className="archive-delete-target"><Archive size={18} /><span><small>资料库根目录</small><strong>{archiveDelete.archive.name}</strong></span></div>
        {archiveDeleteLoading ? <div className="archive-delete-loading"><Loader2 className="spin" size={17} />正在核对关联数据…</div> : archiveDelete.impact && <div className="archive-delete-impact"><span><strong>{archiveDelete.impact.material_count}</strong><small>资料索引</small></span><span><strong>{archiveDelete.impact.document_count}</strong><small>平台文件副本</small></span><span><strong>{archiveDelete.impact.design_count}</strong><small>教学设计</small></span><span><strong>{archiveDelete.impact.composition_count}</strong><small>教学资料包</small></span><span><strong>{archiveDelete.impact.run_count}</strong><small>关联会话</small></span></div>}
        <div className="organize-delete-warning"><AlertCircle size={18} /><span><strong>确认从平台删除“{archiveDelete.archive.name}”</strong><small>此操作不可撤销，但不会删除电脑上的本机源文件和源文件夹。</small></span></div>
        {error && <div className="hub-dialog-error" role="alert"><X size={14} /><span>{error}</span></div>}
        <footer><button type="button" className="secondary-button" disabled={archiveDeleting} onClick={() => setArchiveDelete(null)}>取消</button><button type="button" className="hub-danger-button" disabled={archiveDeleting || archiveDeleteLoading || !archiveDelete.impact} onClick={() => void confirmArchiveDeletion()}>{archiveDeleting ? <Loader2 className="spin" size={15} /> : <Trash2 size={14} />}{archiveDeleting ? '正在删除关联数据…' : '确认从平台删除'}</button></footer>
      </section></div>}
      {organizeDialog && <div className="hub-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !mutating) setOrganizeDialog(null); }}><section ref={organizeDialogElement} className="hub-dialog hub-organize-dialog" role="dialog" aria-modal="true" aria-labelledby="hub-organize-dialog-title">
        <header><div>{organizeDialog.mode === 'create' || organizeDialog.mode === 'create-root' ? <FolderPlus size={18} /> : organizeDialog.mode === 'delete-folder' || organizeDialog.mode === 'delete-source' || organizeDialog.mode === 'delete-blocks' ? <Trash2 size={18} /> : organizeDialog.mode.startsWith('move') ? <Move size={18} /> : <Pencil size={18} />}<span><strong id="hub-organize-dialog-title">{organizeDialog.mode === 'create-root' ? '新建顶层文件夹' : organizeDialog.mode === 'rename-root' ? '重命名顶层文件夹' : organizeDialog.mode === 'create' ? '新建子文件夹' : organizeDialog.mode === 'rename-folder' ? '重命名文件夹' : organizeDialog.mode === 'rename-block' ? '重命名资料' : organizeDialog.mode === 'delete-source' ? '移除来源文件夹' : organizeDialog.mode === 'delete-folder' ? '删除文件夹' : organizeDialog.mode === 'delete-blocks' ? '删除原始文件' : '移动到文件夹'}</strong><small>{organizeDialog.mode === 'create-root' ? '当前位置：资料库根目录；将与现有顶层文件夹同级' : organizeDialog.mode === 'rename-root' ? `当前名称：${organizeDialog.currentName}；教学元数据与资料引用保持不变` : organizeDialog.mode === 'create' ? `当前位置：${organizeDialog.parentLabel}` : organizeDialog.mode === 'delete-folder' || organizeDialog.mode === 'delete-source' || organizeDialog.mode === 'delete-blocks' ? '只删除平台记录与平台副本，不删除本机源文件' : organizeDialog.mode === 'move-blocks' && organizeDialog.syncMode === 'copy' ? '复制本机文件到目标目录，原文件继续保留' : organizeDialog.mode === 'move-blocks' && organizeDialog.syncMode === 'move' ? '移动电脑上的原文件，原路径将不再保留' : '只调整平台内目录，原始文件和引用保持不变'}</small></span></div><button type="button" disabled={mutating} onClick={() => setOrganizeDialog(null)} aria-label="关闭目录操作"><X size={17} /></button></header>
        {(organizeDialog.mode === 'create-root' || organizeDialog.mode === 'rename-root' || organizeDialog.mode === 'create' || organizeDialog.mode === 'rename-folder' || organizeDialog.mode === 'rename-block') && <label>{organizeDialog.mode === 'rename-block' ? '资料显示名称' : '文件夹名称'}<input data-dialog-initial-focus name="organize-name" autoComplete="off" value={organizeDialog.name} onChange={(event) => setOrganizeDialog({ ...organizeDialog, name: event.target.value })} placeholder={organizeDialog.mode === 'rename-block' ? '输入资料显示名称…' : '输入文件夹名称…'} onKeyDown={(event) => { if (event.key === 'Enter') void submitOrganize(); }} /></label>}
        {(organizeDialog.mode === 'create-root' || organizeDialog.mode === 'create') && <div className="organize-path-preview"><span>创建后位置</span><strong><Home size={14} />{organizeDialog.mode === 'create-root' ? '资料库' : organizeDialog.parentLabel}<ChevronRight size={12} /><em>{organizeDialog.name.trim() || '新文件夹'}</em></strong></div>}
        {organizeDialog.mode === 'move-blocks' && <><div className="organize-selection-summary"><strong>移动 {organizeDialog.blocks.length} 项资料</strong><span>{organizeDialog.blocks.slice(0, 3).map((item) => item.title).join('、')}{organizeDialog.blocks.length > 3 ? ` 等 ${organizeDialog.blocks.length} 项` : ''}</span></div><label>目标文件夹<select data-dialog-initial-focus name="block-destination" value={organizeDialog.destination} onChange={(event) => setOrganizeDialog({ ...organizeDialog, destination: event.target.value, syncMode: 'platform' })}><option value="">恢复到原文件路径</option>{unitFolders.map((folder) => { const parts = folderPaths.get(folder.id) || [folder.name]; return <option key={folder.id} value={folder.id}>{parts.length ? `主目录 / ${parts.join(' / ')}` : '主目录'}</option>; })}</select></label><div className="organize-sync-choice"><span>是否同步电脑上的文件</span><div role="radiogroup" aria-label="本机文件同步方式"><button type="button" role="radio" aria-checked={organizeDialog.syncMode === 'platform'} className={organizeDialog.syncMode === 'platform' ? 'active' : ''} onClick={() => setOrganizeDialog({ ...organizeDialog, syncMode: 'platform' })}><Database size={14} /><span><strong>仅平台整理</strong><small>不改动本机</small></span></button><button type="button" role="radio" aria-checked={organizeDialog.syncMode === 'copy'} disabled={!canTransferLocally(organizeDialog.blocks, organizeDialog.destination)} className={organizeDialog.syncMode === 'copy' ? 'active' : ''} onClick={() => setOrganizeDialog({ ...organizeDialog, syncMode: 'copy' })}><Copy size={14} /><span><strong>复制本机文件</strong><small>保留原文件</small></span></button><button type="button" role="radio" aria-checked={organizeDialog.syncMode === 'move'} disabled={!canTransferLocally(organizeDialog.blocks, organizeDialog.destination)} className={organizeDialog.syncMode === 'move' ? 'active danger' : 'danger'} onClick={() => setOrganizeDialog({ ...organizeDialog, syncMode: 'move' })}><Move size={14} /><span><strong>移动本机原文件</strong><small>原路径不保留</small></span></button></div>{!canTransferLocally(organizeDialog.blocks, organizeDialog.destination) && <small>本机同步仅适用于同一本地来源内的目标文件夹。</small>}{organizeDialog.syncMode === 'move' && <div className="organize-move-warning"><AlertCircle size={15} />确认后将移动电脑上的原文件，此操作会改变本机目录。</div>}</div></>}
        {organizeDialog.mode === 'move-folder' && <label>目标位置<select data-dialog-initial-focus name="folder-destination" value={organizeDialog.destination} onChange={(event) => setOrganizeDialog({ ...organizeDialog, destination: event.target.value })}><option value="">主目录</option>{unitFolders.filter((folder) => !unavailableMoveFolderIds.has(folder.id)).map((folder) => { const parts = folderPaths.get(folder.id) || [folder.name]; return <option key={folder.id} value={`folder:${folder.id}`}>{parts.length ? `主目录 / ${parts.join(' / ')}` : '主目录'}</option>; })}</select></label>}
        {organizeDialog.mode === 'delete-folder' && <div className="organize-delete-warning"><Trash2 size={18} /><span><strong>删除“{organizeDialog.folder.name}”及其中内容</strong><small>该文件夹的子文件夹、平台文件副本和目录引用将一并删除。此操作不可撤销。</small></span></div>}
        {organizeDialog.mode === 'delete-source' && <div className="organize-delete-warning"><Trash2 size={18} /><span><strong>从平台移除“{organizeDialog.folder.name}”</strong><small>该来源下的平台记录、目录引用与上传副本将移除；关联路径中的本机文件和文件夹不会被删除。点击确认即可，无需输入文字。</small></span></div>}
        {organizeDialog.mode === 'delete-blocks' && <div className="organize-delete-warning"><Trash2 size={18} /><span><strong>删除 {organizeDialog.blocks.length} 个原始文件</strong><small>{organizeDialog.blocks.slice(0, 3).map((item) => item.title).join('、')}{organizeDialog.blocks.length > 3 ? ` 等 ${organizeDialog.blocks.length} 项` : ''}。平台副本和后续目录引用将一并删除。</small></span></div>}
        {error && <div className="hub-dialog-error" role="alert"><X size={14} /><span>{error}</span></div>}
        <footer><button type="button" className="secondary-button" disabled={mutating} onClick={() => setOrganizeDialog(null)}>取消</button><button type="button" className={organizeDialog.mode === 'delete-folder' || organizeDialog.mode === 'delete-source' || organizeDialog.mode === 'delete-blocks' || organizeDialog.mode === 'move-blocks' && organizeDialog.syncMode === 'move' ? 'hub-danger-button' : 'hub-connect-button'} disabled={mutating || (('name' in organizeDialog) && !organizeDialog.name.trim())} onClick={() => void submitOrganize()}>{mutating ? <Loader2 className="spin" size={15} /> : organizeDialog.mode === 'delete-folder' || organizeDialog.mode === 'delete-source' || organizeDialog.mode === 'delete-blocks' ? <Trash2 size={14} /> : organizeDialog.mode === 'move-blocks' && organizeDialog.syncMode === 'move' ? <Move size={14} /> : <Check size={14} />}{mutating ? '正在处理…' : organizeDialog.mode === 'delete-source' ? '确认从平台移除' : organizeDialog.mode === 'delete-folder' || organizeDialog.mode === 'delete-blocks' ? '确认删除' : organizeDialog.mode === 'move-blocks' && organizeDialog.syncMode === 'move' ? '确认移动本机文件' : organizeDialog.mode === 'move-blocks' && organizeDialog.syncMode === 'copy' ? '确认复制本机文件' : '确认'}</button></footer>
      </section></div>}
      {localSyncOpen && <div className="hub-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !localSyncing) setLocalSyncOpen(false); }}><section ref={localSyncDialog} className="hub-dialog local-sync-dialog" role="dialog" aria-modal="true" aria-labelledby="hub-local-sync-title">
        <header><div><FolderSync size={18} /><span><strong id="hub-local-sync-title">同步到本地</strong><small>仅处理本次页面中新建和上传的内容</small></span></div><button type="button" disabled={localSyncing} onClick={() => setLocalSyncOpen(false)} aria-label="关闭同步确认"><X size={17} /></button></header>
        <p className="hub-deferred-note"><AlertCircle size={14} />同步会在关联的本机目录中创建文件夹或写入上传文件；不会覆盖同名文件。浏览器上传待办只在本次页面打开期间有效。</p>
        <div className="local-sync-list" role="list">{pendingLocalSyncs.map((item) => <article key={item.id} className="local-sync-item" role="listitem">
          <span className={`local-sync-kind ${item.kind}`}>{item.kind === 'folder' ? <FolderPlus size={16} /> : <Upload size={16} />}</span>
          <div><strong>{item.label}</strong><small className="local-sync-path">{item.pathLabel}</small><small>{item.kind === 'folder' ? '将在本机创建对应目录' : `${item.files.length} 个文件 · ${item.directoryPaths.length} 个空目录`}</small></div>
          <button type="button" disabled={localSyncing} onClick={() => setPendingLocalSyncs((current) => current.filter((change) => change.id !== item.id))} title="放弃此同步记录" aria-label={`放弃同步${item.label}`}><X size={14} /></button>
        </article>)}</div>
        {!pendingLocalSyncs.length && <div className="local-sync-empty"><CheckCircle2 size={18} />本次变更均已处理</div>}
        {error && <div className="hub-dialog-error" role="alert"><X size={14} /><span>{error}</span></div>}
        <footer><button type="button" className="secondary-button" disabled={localSyncing} onClick={() => setLocalSyncOpen(false)}>取消</button><button type="button" className="hub-connect-button" disabled={localSyncing || !pendingLocalSyncs.length} onClick={() => void executePendingLocalSyncs()}>{localSyncing ? <Loader2 className="spin" size={15} /> : <FolderSync size={15} />}{localSyncing ? '正在同步…' : `同步全部 ${pendingLocalSyncs.length} 项`}</button></footer>
      </section></div>}
      {sourceDiff && <div className="hub-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !sourceReconciling) setSourceDiff(null); }}><section ref={sourceDiffDialog} className="hub-dialog source-diff-dialog" role="dialog" aria-modal="true" aria-labelledby="source-diff-title">
        <header><div><RefreshCw size={18} /><span><strong id="source-diff-title">刷新与同步来源</strong><small>{sourceDiff.source_name} · {sourceDiff.local_root}</small></span></div><button type="button" disabled={!!sourceReconciling} onClick={() => setSourceDiff(null)} aria-label="关闭来源差异"><X size={17} /></button></header>
        <div className="source-diff-summary"><span><strong>{sourceDiff.local_changes}</strong><small>本地变更</small></span><span><strong>{sourceDiff.platform_changes}</strong><small>平台变更</small></span><span className={sourceDiff.blocked_restores ? 'warning' : ''}><strong>{sourceDiff.blocked_restores}</strong><small>无法反向恢复</small></span></div>
        {sourceDiff.items.length ? <div className="source-diff-list" role="list">{sourceDiff.items.map((item) => {
          const statusText = item.status === 'local_added' ? '本地新增文件' : item.status === 'local_removed' ? '本地已删除' : item.status === 'local_changed' ? '本地已修改' : item.status === 'platform_deleted' ? '平台已删除' : item.status === 'local_directory_added' ? '本地新增目录' : '平台新增目录';
          return <article key={`${item.status}:${item.path}`} role="listitem"><span className={`source-diff-status ${item.status}`}>{item.kind === 'directory' ? <Folder size={14} /> : <File size={14} />}{statusText}</span><strong title={item.path}>{item.path}</strong>{(item.status === 'local_removed' || item.status === 'local_changed') && !item.can_restore ? <em>平台无原件，无法恢复本地</em> : <small>{item.kind === 'file' ? `${item.local_size ?? item.platform_size ?? 0} B` : '目录'}</small>}</article>;
        })}</div> : <div className="local-sync-empty"><CheckCircle2 size={18} />本地目录与平台记录一致</div>}
        <div className="source-sync-directions">
          <button type="button" disabled={!!sourceReconciling || !sourceDiff.items.length} onClick={() => void reconcileSource('update_platform')}><Database size={17} /><span><strong>更新平台</strong><small>以本地目录为准，平台采纳本地新增、修改和删除</small></span>{sourceReconciling === 'update_platform' ? <Loader2 className="spin" size={16} /> : <ChevronRight size={16} />}</button>
          <button type="button" disabled={!!sourceReconciling || !sourceDiff.items.length} onClick={() => void reconcileSource('update_local')}><FolderSync size={17} /><span><strong>更新本地</strong><small>以平台记录为准；删除本地新增项，执行平台删除，无法恢复项会跳过</small></span>{sourceReconciling === 'update_local' ? <Loader2 className="spin" size={16} /> : <ChevronRight size={16} />}</button>
        </div>
        {error && <div className="hub-dialog-error" role="alert"><X size={14} /><span>{error}</span></div>}
        <footer><button type="button" className="secondary-button" disabled={!!sourceReconciling} onClick={() => setSourceDiff(null)}>取消</button></footer>
      </section></div>}
      {error && <div className="hub-dialog-error" role="alert"><X size={14} /><span>{error}</span></div>}
    </main>
  );
}

function FileRow({ item, selected, focused, menuOpen, canSystemOpen, onToggle, onSystemOpen, onInspect, onReload, onMenu, onRename, onMove, onDelete }: { item: DataHubBlock; selected: boolean; focused: boolean; menuOpen: boolean; canSystemOpen: boolean; onToggle: () => void; onSystemOpen: () => void; onInspect: () => void; onReload: () => void; onMenu: () => void; onRename: () => void; onMove: () => void; onDelete: () => void }) {
  return <div role="listitem" aria-selected={focused} className={`directory-file-row ${selected ? 'selected' : ''} ${focused ? 'focused' : ''} ${menuOpen ? 'menu-open' : ''}`}>
    <button type="button" className="hub-check" onClick={onToggle} aria-pressed={selected} aria-label={selected ? `取消选择${item.title}` : `选择${item.title}`}>{selected ? <Check size={14} /> : <Square size={14} />}</button>
    <span className={`file-icon kind-${item.kind}`}><File size={17} /><small>{extensionOf(item.title)}</small></span>
    <button type="button" className="hub-file-copy" onClick={onSystemOpen} onDoubleClick={() => { if (canSystemOpen) onSystemOpen(); }} title={canSystemOpen ? '使用系统默认程序打开' : '查看索引信息；备课选定后才导入原件'}><strong>{item.title}</strong><small title={item.locator}>{item.source_name && item.source_name !== item.title ? item.source_name : item.locator}</small></button>
    <span className="hub-kind kind-original">{categoryLabels[item.category || 'other'] || '其他'}</span>
    <time dateTime={item.updated_at}>{formatDate(typeof item.modified_at === 'number' ? new Date(item.modified_at).toISOString() : String(item.modified_at || item.updated_at))}</time>
    <button type="button" onClick={onMenu} aria-label={`管理${item.title}`} aria-expanded={menuOpen} title="更多操作"><MoreHorizontal size={15} /></button>
    {menuOpen && <div className="hub-item-menu file-menu">{canSystemOpen && <button type="button" onClick={onSystemOpen}><ExternalLink size={13} />系统打开</button>}<button type="button" onClick={onInspect}><FileSearch size={13} />文件信息</button>{item.source_kind === 'local' && <button type="button" onClick={onReload}><RotateCw size={13} />重新加载</button>}<button type="button" onClick={onRename}><Pencil size={13} />重命名</button><button type="button" onClick={onMove}><Move size={13} />移动到</button><button type="button" className="danger" onClick={onDelete}><Trash2 size={13} />从平台删除</button></div>}
  </div>;
}
