import { useImportStore, getStageProgress } from '../../../stores/importStore';
import { cn } from '../../../utils/cn';

const STAGES = [
  { id: 'uploading', label: '上传文件', icon: '📤' },
  { id: 'extracting', label: '提取内容', icon: '📄' },
  { id: 'analyzing', label: '分析知识点', icon: '🔍' },
  { id: 'building', label: '构建知识图谱', icon: '🧠' },
] as const;

export function UploadProgress() {
  const { uploading, uploadProgress, currentFile, parseStage, parseProgress, parseMessage } = useImportStore();

  const totalProgress = getStageProgress(parseStage, parseProgress);

  if (!uploading && parseStage === 'idle') {
    return null;
  }

  return (
    <div className="w-full bg-white rounded-2xl shadow-lg border border-slate-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center text-xl">
            {parseStage === 'completed' ? '✅' : parseStage === 'failed' ? '❌' : '⚙️'}
          </div>
          <div>
            <h3 className="font-semibold text-slate-800">文档解析</h3>
            <p className="text-sm text-slate-500">{currentFile?.name || '等待上传...'}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-blue-600">{Math.round(totalProgress)}%</div>
          <div className="text-xs text-slate-400">{parseMessage}</div>
        </div>
      </div>

      {/* Overall progress bar */}
      <div className="h-3 bg-slate-100 rounded-full overflow-hidden mb-6">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-500',
            parseStage === 'failed' ? 'bg-red-500' :
            parseStage === 'completed' ? 'bg-emerald-500' :
            'bg-gradient-to-r from-blue-500 to-indigo-600'
          )}
          style={{ width: `${totalProgress}%` }}
        />
      </div>

      {/* Stage indicators */}
      <div className="flex justify-between">
        {STAGES.map((stage) => {
          const stageStatus = getStageStatus(stage.id, parseStage);

          return (
            <div key={stage.id} className="flex flex-col items-center">
              <div
                className={cn(
                  'w-12 h-12 rounded-full flex items-center justify-center text-xl transition-all duration-300',
                  stageStatus === 'completed' && 'bg-emerald-500 text-white scale-110',
                  stageStatus === 'active' && 'bg-blue-500 text-white animate-pulse ring-4 ring-blue-200',
                  stageStatus === 'pending' && 'bg-slate-200 text-slate-400'
                )}
              >
                {stageStatus === 'completed' ? '✓' : stage.icon}
              </div>
              <span className={cn(
                'mt-2 text-xs font-medium',
                stageStatus === 'completed' && 'text-emerald-600',
                stageStatus === 'active' && 'text-blue-600',
                stageStatus === 'pending' && 'text-slate-400'
              )}>
                {stage.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Connection lines between stages */}
      <div className="flex justify-between mt-[-2.4rem] px-8 relative z-10">
        {[0, 1, 2].map((i) => {
          const nextStageId = STAGES[i + 1].id;
          const isCompleted = getStageStatus(nextStageId, parseStage) !== 'pending';

          return (
            <div
              key={i}
              className={cn(
                'flex-1 h-0.5 mx-4',
                isCompleted ? 'bg-emerald-500' : 'bg-slate-200'
              )}
            />
          );
        })}
      </div>

      {/* Upload progress for file upload stage */}
      {parseStage === 'uploading' && (
        <div className="mt-6 p-4 bg-slate-50 rounded-xl">
          <div className="flex items-center justify-between text-sm text-slate-600">
            <span className="flex items-center gap-2">
              <span className="animate-spin">⏳</span>
              上传中...
            </span>
            <span>{Math.round(uploadProgress)}%</span>
          </div>
          <div className="mt-2 h-2 bg-slate-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function getStageStatus(
  stageId: string,
  currentStage: string
): 'completed' | 'active' | 'pending' {
  const stageOrder = ['uploading', 'extracting', 'analyzing', 'building', 'completed'];
  const currentIndex = stageOrder.indexOf(currentStage);
  const stageIndex = stageOrder.indexOf(stageId);

  if (stageIndex < currentIndex || currentStage === 'completed') {
    return 'completed';
  }
  if (stageIndex === currentIndex) {
    return 'active';
  }
  return 'pending';
}