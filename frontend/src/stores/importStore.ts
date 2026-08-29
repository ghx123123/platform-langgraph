import { create } from 'zustand';
import type { ParseStage, KnowledgePoint, ImportResult } from '../types/visualization';

interface ImportState {
  // Upload state
  uploading: boolean;
  uploadProgress: number;
  currentFile: File | null;

  // Parse state
  parseStage: ParseStage;
  parseProgress: number;
  parseMessage: string;

  // Extracted data
  knowledgePoints: KnowledgePoint[];

  // Import result
  importResult: ImportResult | null;

  // Error
  error: string | null;

  // Actions
  startUpload: (file: File) => void;
  setUploadProgress: (progress: number) => void;
  setParseStage: (stage: ParseStage, message?: string) => void;
  setParseProgress: (progress: number) => void;
  setKnowledgePoints: (points: KnowledgePoint[]) => void;
  setImportResult: (result: ImportResult) => void;
  setError: (error: string) => void;
  reset: () => void;
}

const initialState = {
  uploading: false,
  uploadProgress: 0,
  currentFile: null,
  parseStage: 'idle' as ParseStage,
  parseProgress: 0,
  parseMessage: '',
  knowledgePoints: [],
  importResult: null,
  error: null,
};

export const useImportStore = create<ImportState>((set) => ({
  ...initialState,

  startUpload: (file: File) => {
    set({
      uploading: true,
      uploadProgress: 0,
      currentFile: file,
      parseStage: 'uploading',
      parseMessage: '正在上传文件...',
      error: null,
    });
  },

  setUploadProgress: (progress: number) => {
    set({ uploadProgress: progress });
  },

  setParseStage: (stage: ParseStage, message?: string) => {
    const defaultMessages: Record<ParseStage, string> = {
      idle: '',
      uploading: '正在上传文件...',
      extracting: '正在提取文档内容...',
      analyzing: '正在分析知识点...',
      building: '正在构建知识图谱...',
      completed: '解析完成',
      failed: '解析失败',
    };

    set({
      parseStage: stage,
      parseMessage: message || defaultMessages[stage],
    });
  },

  setParseProgress: (progress: number) => {
    set({ parseProgress: progress });
  },

  setKnowledgePoints: (points: KnowledgePoint[]) => {
    set({ knowledgePoints: points });
  },

  setImportResult: (result: ImportResult) => {
    set({
      importResult: result,
      uploading: false,
      parseStage: 'completed',
      parseProgress: 100,
    });
  },

  setError: (error: string) => {
    set({
      error,
      uploading: false,
      parseStage: 'failed',
    });
  },

  reset: () => {
    set(initialState);
  },
}));

// Helper to get stage progress percentage (0-100)
export function getStageProgress(stage: ParseStage, progress: number): number {
  const stageMapping: Record<ParseStage, { start: number; end: number }> = {
    idle: { start: 0, end: 0 },
    uploading: { start: 0, end: 20 },
    extracting: { start: 20, end: 40 },
    analyzing: { start: 40, end: 70 },
    building: { start: 70, end: 100 },
    completed: { start: 100, end: 100 },
    failed: { start: 0, end: 0 },
  };

  const { start, end } = stageMapping[stage];
  return start + (end - start) * (progress / 100);
}