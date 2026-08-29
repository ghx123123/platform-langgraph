// DocumentUpload.tsx - 辩论文档上传
import { useState, useRef, useCallback } from 'react';
import { KnowledgePoint } from '../types';

interface DocumentUploadProps {
  onUploadComplete: (docId: string, parseResult: any, sessionId?: string) => void;
  onClose?: () => void;
  compact?: boolean;
  mode?: 'debate' | 'teaching';
}

interface ParseResult {
  knowledge_points: KnowledgePoint[];
  course_name: string;
  chapter_title: string;
  raw_text: string;
}

export function DocumentUpload({ onUploadComplete, onClose, compact = false, mode = 'debate' }: DocumentUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      const ext = selectedFile.name.split('.').pop()?.toLowerCase();
      if (ext && ['pdf', 'docx', 'md'].includes(ext)) {
        setFile(selectedFile);
        setError(null);
        setParseResult(null);
      } else {
        setError('不支持的文件格式，请上传 PDF/DOCX/MD');
        setFile(null);
      }
    }
  }, []);

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || '上传失败');
      }

      const data = await res.json();
      setParseResult(data.parse_result);

      // 只有辩论模式才自动创建会话，教学模式直接返回文档信息
      if (mode === 'debate') {
        const sessionRes = await fetch('/api/debate/sessions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: new URLSearchParams({
            title: data.parse_result?.course_name || file.name,
            document_id: data.document_id,
            max_rounds: '5',
          }),
        });

        if (sessionRes.ok) {
          const sessionData = await sessionRes.json();
          // 返回辩论会话ID和知识点，第三个参数传递sessionId用于自动进入辩论
          onUploadComplete(data.document_id, data.parse_result, sessionData.session.id);
        }
      } else {
        // 教学模式：直接返回文档信息
        onUploadComplete(data.document_id, data.parse_result);
      }
    } catch (e) {
      console.error('[DocumentUpload] Upload error:', e);
      setError(e instanceof Error ? e.message : '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile) {
      const ext = droppedFile.name.split('.').pop()?.toLowerCase();
      if (ext && ['pdf', 'docx', 'md'].includes(ext)) {
        setFile(droppedFile);
        setError(null);
        setParseResult(null);
      } else {
        setError('不支持的文件格式，请上传 PDF/DOCX/MD');
        setFile(null);
      }
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const triggerFileInput = () => {
    console.log('[DocumentUpload] Triggering file input click');
    if (fileInputRef.current) {
      fileInputRef.current.click();
    } else {
      console.error('[DocumentUpload] File input ref is null');
    }
  };

  const content = (
    <>
      {/* Content */}
      <div className="p-6 overflow-y-auto max-h-[60vh]">
        {/* Hidden file input - outside of click area */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        
        {/* Drop Zone - using button for better accessibility */}
        <button
          type="button"
          onClick={triggerFileInput}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`w-full border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200 ${
            isDragging
              ? 'border-blue-500 bg-blue-50 scale-[1.02]'
              : file
                ? 'border-emerald-400 bg-emerald-50'
                : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
          }`}
        >
          {file ? (
            <div className="flex items-center justify-center gap-3">
              <span className="text-3xl">📎</span>
              <div className="text-left">
                <p className="font-medium text-slate-800">{file.name}</p>
                <p className="text-sm text-slate-500">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="text-4xl mb-3">{isDragging ? '📥' : '📁'}</div>
              <p className="text-lg mb-1 font-medium text-slate-700">
                {isDragging ? '释放以上传文件' : '点击或拖拽文件到此处'}
              </p>
              <p className="text-sm text-slate-500">支持 PDF、DOCX、MD 格式</p>
            </>
          )}
        </button>

        {/* Error */}
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm">
            {error}
          </div>
        )}

        {/* Parse Result */}
        {parseResult && (
          <div className="mt-6">
            <h3 className="font-semibold mb-3 flex items-center gap-2 text-slate-800">
              <span>📚</span> 解析结果
            </h3>
            <div className="bg-slate-50 rounded-xl p-4 space-y-4 border border-slate-200">
              <div>
                <p className="text-sm text-slate-500">课程名称</p>
                <p className="font-medium text-slate-800">{parseResult.course_name}</p>
              </div>
              {parseResult.chapter_title && (
                <div>
                  <p className="text-sm text-slate-500">章节标题</p>
                  <p className="font-medium text-slate-800">{parseResult.chapter_title}</p>
                </div>
              )}
              <div>
                <p className="text-sm text-slate-500 mb-2">
                  提取的知识点 ({parseResult.knowledge_points?.length || 0}个)
                </p>
                {parseResult.knowledge_points && parseResult.knowledge_points.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {parseResult.knowledge_points.slice(0, 10).map((kp, i) => (
                      <span
                        key={i}
                        className={`px-2.5 py-1 rounded-lg text-xs font-medium ${
                          kp.is_key_point
                            ? 'bg-amber-100 text-amber-700 border border-amber-200'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {kp.title}
                      </span>
                    ))}
                    {parseResult.knowledge_points.length > 10 && (
                      <span className="text-xs text-slate-500 px-2 py-1">
                        +{parseResult.knowledge_points.length - 10} 更多
                      </span>
                    )}
                  </div>
                ) : (
                  <p className="text-slate-500 text-sm">未能提取知识点</p>
                )}
              </div>
            </div>

            {/* Status Info */}
            <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded-xl">
              <p className="text-sm text-emerald-700 flex items-center gap-2">
                <span>✅</span> {mode === 'debate' ? '辩论会话已创建' : '文档解析完成，请点击下方按钮创建教学会话'}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200 bg-white">
        {onClose && (
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl transition-colors border border-slate-200"
          >
            取消
          </button>
        )}
        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 disabled:from-slate-300 disabled:to-slate-400 disabled:cursor-not-allowed rounded-xl flex items-center gap-2 transition-all shadow-md"
        >
          {uploading ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              解析中...
            </>
          ) : (
            <>
              <span>📤</span> 上传并解析
            </>
          )}
        </button>
      </div>
    </>
  );

  if (compact) {
    // Compact mode: just return the content without modal wrapper
    return content;
  }

  // Full modal mode
  return (
    <div className="fixed inset-0 bg-slate-900/30 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-xl border border-slate-200/60 w-full max-w-2xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="text-xl font-bold flex items-center gap-3 text-slate-800">
            <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-xl flex items-center justify-center text-xl text-white shadow-md">
              📄
            </div>
            {mode === 'teaching' ? '上传教学文档' : '上传辩论文档'}
          </h2>
          {onClose && (
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            >
              ✕
            </button>
          )}
        </div>
        {content}
      </div>
    </div>
  );
}

// Default export for lazy loading
export default DocumentUpload;
