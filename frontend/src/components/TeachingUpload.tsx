// TeachingUpload.tsx - 文档上传和教学会话创建
import { useState } from 'react';
import { DocumentUpload } from './DocumentUpload';

interface TeachingUploadProps {
  onUploadComplete: (sessionId: string) => void;
  onClose: () => void;
}

export function TeachingUpload({ onUploadComplete, onClose }: TeachingUploadProps) {
  const [step, setStep] = useState<'upload' | 'config' | 'creating'>('upload');
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [maxIterations, setMaxIterations] = useState(3);
  const [parsedResult, setParsedResult] = useState<any>(null);
  const [isCreating, setIsCreating] = useState(false);

  const handleUploadComplete = (docId: string, parseResult: any) => {
    setDocumentId(docId);
    setParsedResult(parseResult);
    setTitle(parseResult?.course_name || '教学课程');
    setStep('config');
  };

  const handleCreateSession = async () => {
    if (!title.trim()) return;

    setIsCreating(true);
    try {
      const formData = new URLSearchParams();
      formData.append('title', title);
      formData.append('max_iterations', String(maxIterations));
      if (documentId) {
        formData.append('document_id', documentId);
      }

      const res = await fetch('/api/teaching/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
      });

      if (!res.ok) throw new Error('Failed to create session');

      const data = await res.json();
      onUploadComplete(data.session.id);
    } catch (e) {
      console.error('[TeachingUpload] Failed to create session:', e);
      alert('创建教学会话失败');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-xl w-full max-w-lg mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-xl font-bold">新建教学模拟</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {step === 'upload' && (
            <DocumentUpload
              onUploadComplete={handleUploadComplete}
              onClose={onClose}
              compact
              mode="teaching"
            />
          )}

          {step === 'config' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">
                  课程标题
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  placeholder="输入课程标题"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-2">
                  教学迭代次数
                </label>
                <select
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-blue-500"
                >
                  <option value={1}>1 轮</option>
                  <option value={2}>2 轮</option>
                  <option value={3}>3 轮</option>
                  <option value={4}>4 轮</option>
                  <option value={5}>5 轮</option>
                </select>
              </div>

              {parsedResult && parsedResult.knowledge_points && (
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-2">
                    解析到的知识点 ({parsedResult.knowledge_points.length} 个)
                  </label>
                  <div className="max-h-40 overflow-y-auto bg-gray-700 rounded-lg p-3 space-y-2">
                    {parsedResult.knowledge_points.slice(0, 10).map((kp: any, i: number) => (
                      <div key={i} className="text-sm text-gray-300">
                        • {kp.title}
                      </div>
                    ))}
                    {parsedResult.knowledge_points.length > 10 && (
                      <div className="text-sm text-gray-500">
                        ... 还有 {parsedResult.knowledge_points.length - 10} 个
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setStep('upload')}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white transition-colors"
                >
                  重新上传文档
                </button>
                <button
                  onClick={handleCreateSession}
                  disabled={!title.trim() || isCreating}
                  className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-white transition-colors"
                >
                  {isCreating ? '创建中...' : '创建教学会话'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Default export for lazy loading
export default TeachingUpload;
