// ObjectivesAssessmentView.tsx - 学习目标匹配度展示组件
import { useState, useEffect, useCallback } from 'react';
import {
  fetchObjectives,
  fetchObjectiveAssessment,
  createObjective,
  deleteObjective,
  triggerAssessment,
  getMatchLevelConfig,
  getObjectiveTypeConfig,
  getPriorityConfig,
  LearningObjective,
  ObjectiveAssessment,
  AssessmentSummary,
  ObjectiveType,
  PriorityLevel,
} from '../../services/objectivesApi';

interface ObjectivesAssessmentViewProps {
  sessionId: string;
}

export function ObjectivesAssessmentView({ sessionId }: ObjectivesAssessmentViewProps) {
  // 数据状态
  const [objectives, setObjectives] = useState<LearningObjective[]>([]);
  const [assessments, setAssessments] = useState<ObjectiveAssessment[]>([]);
  const [summary, setSummary] = useState<AssessmentSummary>({
    avg_score: 0,
    total_objectives: 0,
    assessed_count: 0,
    covered_count: 0,
    uncovered_count: 0,
  });

  // UI状态
  const [loading, setLoading] = useState(true);
  const [assessing, setAssessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [expandedObjective, setExpandedObjective] = useState<string | null>(null);

  // 表单状态
  const [newObjectiveDescription, setNewObjectiveDescription] = useState('');
  const [newObjectiveType, setNewObjectiveType] = useState<ObjectiveType>('knowledge');
  const [newObjectivePriority, setNewObjectivePriority] = useState<PriorityLevel>('medium');

  // 加载数据
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [objectivesData, assessmentData] = await Promise.all([
        fetchObjectives(sessionId),
        fetchObjectiveAssessment(sessionId),
      ]);

      setObjectives(objectivesData);
      setAssessments(assessmentData.objective_assessments);
      setSummary(assessmentData.summary);
    } catch (e) {
      console.error('[ObjectivesAssessmentView] 加载数据失败:', e);
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // 初始加载
  useEffect(() => {
    loadData();
  }, [loadData]);

  // 触发评估
  const handleTriggerAssessment = async () => {
    try {
      setAssessing(true);
      setError(null);

      const data = await triggerAssessment(sessionId);
      setAssessments(data.objective_assessments);
      setSummary(data.summary);
    } catch (e) {
      console.error('[ObjectivesAssessmentView] 触发评估失败:', e);
      setError(e instanceof Error ? e.message : '触发评估失败');
    } finally {
      setAssessing(false);
    }
  };

  // 添加目标
  const handleAddObjective = async () => {
    if (!newObjectiveDescription.trim()) return;

    try {
      setError(null);
      await createObjective(sessionId, {
        description: newObjectiveDescription,
        objective_type: newObjectiveType,
        priority: newObjectivePriority,
      });

      // 重置表单
      setNewObjectiveDescription('');
      setNewObjectiveType('knowledge');
      setNewObjectivePriority('medium');
      setShowAddDialog(false);

      // 重新加载数据
      await loadData();
    } catch (e) {
      console.error('[ObjectivesAssessmentView] 添加目标失败:', e);
      setError(e instanceof Error ? e.message : '添加目标失败');
    }
  };

  // 删除目标
  const handleDeleteObjective = async (objectiveId: string) => {
    if (!confirm('确定要删除这个学习目标吗？')) return;

    try {
      setError(null);
      await deleteObjective(sessionId, objectiveId);
      await loadData();
    } catch (e) {
      console.error('[ObjectivesAssessmentView] 删除目标失败:', e);
      setError(e instanceof Error ? e.message : '删除目标失败');
    }
  };

  // 获取目标的评估结果
  const getAssessmentForObjective = (objectiveId: string): ObjectiveAssessment | undefined => {
    return assessments.find(a => a.objective_id === objectiveId);
  };

  // 切换展开状态
  const toggleExpand = (objectiveId: string) => {
    setExpandedObjective(expandedObjective === objectiveId ? null : objectiveId);
  };

  // 获取未覆盖的目标
  const getUncoveredObjectives = (): LearningObjective[] => {
    return objectives.filter(obj => {
      const assessment = getAssessmentForObjective(obj.id);
      return !assessment || assessment.coverage_score < 70;
    });
  };

  // 渲染进度条
  const renderProgressBar = (score: number) => {
    const config = getMatchLevelConfig(score);
    return (
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2.5 bg-slate-200 rounded-full overflow-hidden">
          <div
            className={`h-full ${config.bgColor} transition-all duration-500 ease-out`}
            style={{ width: `${score}%` }}
          />
        </div>
        <span className={`text-sm font-semibold ${config.color} min-w-[3rem] text-right`}>
          {score}%
        </span>
      </div>
    );
  };

  // 渲染统计卡片
  const renderStatCard = (
    title: string,
    value: string | number,
    subtitle: string,
    colorClass: string,
    icon: string
  ) => (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-500">{title}</p>
          <p className={`text-2xl font-bold ${colorClass} mt-1`}>{value}</p>
          <p className="text-xs text-slate-400 mt-1">{subtitle}</p>
        </div>
        <div className={`w-12 h-12 rounded-lg ${colorClass.replace('text-', 'bg-').replace('600', '100')} flex items-center justify-center text-2xl`}>
          {icon}
        </div>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="w-10 h-10 mx-auto mb-3 border-4 border-slate-200 border-t-blue-500 rounded-full animate-spin"></div>
          <p className="text-slate-500 text-sm">加载学习目标...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-slate-50">
      {/* 头部区域 */}
      <div className="bg-white border-b border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-500 rounded-lg flex items-center justify-center text-xl text-white">
              🎯
            </div>
            <div>
              <h2 className="font-bold text-slate-800">学习目标匹配度</h2>
              <p className="text-xs text-slate-500">
                评估教学内容与学习目标的匹配程度
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleTriggerAssessment}
              disabled={assessing || objectives.length === 0}
              className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              {assessing ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                  分析中...
                </>
              ) : (
                <>
                  <span>🔍</span>
                  触发评估
                </>
              )}
            </button>
            <button
              onClick={() => setShowAddDialog(true)}
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              <span>+</span>
              添加目标
            </button>
          </div>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2">
            <span className="text-red-500">⚠️</span>
            <span className="text-sm text-red-600">{error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-red-400 hover:text-red-600"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* 统计概览 */}
      <div className="p-4 grid grid-cols-4 gap-4">
        {renderStatCard(
          '平均匹配度',
          `${summary.avg_score.toFixed(1)}%`,
          `${summary.assessed_count} 个目标已评估`,
          summary.avg_score >= 80 ? 'text-emerald-600' : summary.avg_score >= 50 ? 'text-amber-600' : 'text-red-600',
          '📊'
        )}
        {renderStatCard(
          '已覆盖目标',
          `${summary.covered_count}/${summary.total_objectives}`,
          `${summary.uncovered_count} 个待加强`,
          'text-emerald-600',
          '✓'
        )}
        {renderStatCard(
          '覆盖率',
          summary.total_objectives > 0
            ? `${((summary.covered_count / summary.total_objectives) * 100).toFixed(0)}%`
            : '0%',
          '学习目标达成率',
          'text-blue-600',
          '📈'
        )}
        {renderStatCard(
          '目标总数',
          summary.total_objectives,
          '已定义的学习目标',
          'text-indigo-600',
          '🎯'
        )}
      </div>

      {/* 未覆盖目标警告 */}
      {getUncoveredObjectives().length > 0 && (
        <div className="mx-4 mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-start gap-2">
            <span className="text-amber-500 text-lg">⚠️</span>
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-800">
                发现 {getUncoveredObjectives().length} 个未充分覆盖的学习目标
              </p>
              <p className="text-xs text-amber-600 mt-1">
                建议优化教学内容或调整目标设置，以提高目标覆盖率。
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 目标列表 */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {objectives.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg border border-slate-200 border-dashed">
            <div className="text-4xl mb-3">🎯</div>
            <p className="text-slate-500 font-medium">暂无学习目标</p>
            <p className="text-sm text-slate-400 mt-1">
              点击"添加目标"按钮创建第一个学习目标
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {objectives.map((objective) => {
              const assessment = getAssessmentForObjective(objective.id);
              const score = assessment?.coverage_score || 0;
              const config = getMatchLevelConfig(score);
              const typeConfig = getObjectiveTypeConfig(objective.objective_type);
              const priorityConfig = getPriorityConfig(objective.priority);
              const isExpanded = expandedObjective === objective.id;

              return (
                <div
                  key={objective.id}
                  className={`bg-white rounded-lg border-2 transition-all ${
                    assessment ? config.borderColor : 'border-slate-200'
                  }`}
                >
                  {/* 目标头部 */}
                  <div
                    className="p-4 cursor-pointer hover:bg-slate-50 transition-colors"
                    onClick={() => assessment && toggleExpand(objective.id)}
                  >
                    <div className="flex items-start gap-3">
                      {/* 匹配度指示器 */}
                      <div
                        className={`w-12 h-12 rounded-lg ${config.lightBg} border-2 ${config.borderColor} flex flex-col items-center justify-center shrink-0`}
                      >
                        <span className={`text-lg font-bold ${config.color}`}>
                          {assessment ? score : '-'}
                        </span>
                        <span className="text-[10px] text-slate-500">%</span>
                      </div>

                      {/* 目标信息 */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-medium ${typeConfig.bgColor} ${typeConfig.color} border ${typeConfig.borderColor}`}
                          >
                            {typeConfig.icon} {typeConfig.label}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-medium ${priorityConfig.bgColor} ${priorityConfig.color} border ${priorityConfig.borderColor}`}
                          >
                            {priorityConfig.label}优先级
                          </span>
                          {assessment && (
                            <span
                              className={`px-2 py-0.5 rounded text-xs font-medium ${config.lightBg} ${config.color} border ${config.borderColor}`}
                            >
                              {config.icon} {config.label}
                            </span>
                          )}
                        </div>
                        <p className="text-slate-700 mt-2 text-sm leading-relaxed">
                          {objective.description}
                        </p>

                        {/* 进度条 */}
                        {assessment && (
                          <div className="mt-3">
                            {renderProgressBar(score)}
                          </div>
                        )}
                      </div>

                      {/* 操作按钮 */}
                      <div className="flex items-center gap-1">
                        {assessment && (
                          <span className="text-slate-400 text-sm">
                            {isExpanded ? '▲' : '▼'}
                          </span>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteObjective(objective.id);
                          }}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                          title="删除目标"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* 展开详情 */}
                  {isExpanded && assessment && (
                    <div className={`border-t ${config.borderColor} ${config.lightBg} p-4`}>
                      {/* 评估证据 */}
                      {assessment.evidence && (
                        <div className="mb-4">
                          <h4 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                            <span>📋</span>
                            评估证据
                          </h4>
                          <div className="bg-white rounded-lg border border-slate-200 p-3">
                            <p className="text-sm text-slate-600 whitespace-pre-wrap">
                              {assessment.evidence}
                            </p>
                          </div>
                        </div>
                      )}

                      {/* 改进建议 */}
                      {assessment.suggestions && assessment.suggestions.length > 0 && (
                        <div className="mb-4">
                          <h4 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                            <span>💡</span>
                            改进建议
                          </h4>
                          <ul className="space-y-2">
                            {assessment.suggestions.map((suggestion, idx) => (
                              <li
                                key={idx}
                                className="flex items-start gap-2 text-sm text-slate-600 bg-white rounded-lg border border-slate-200 p-3"
                              >
                                <span className="text-amber-500 shrink-0">•</span>
                                <span>{suggestion}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* 覆盖缺口 */}
                      {assessment.gaps && assessment.gaps.length > 0 && (
                        <div>
                          <h4 className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-2">
                            <span>⚠️</span>
                            覆盖缺口
                          </h4>
                          <ul className="space-y-2">
                            {assessment.gaps.map((gap, idx) => (
                              <li
                                key={idx}
                                className="flex items-start gap-2 text-sm text-red-600 bg-red-50 rounded-lg border border-red-200 p-3"
                              >
                                <span className="shrink-0">✕</span>
                                <span>{gap}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* 评估时间 */}
                      <div className="mt-4 pt-3 border-t border-slate-200">
                        <p className="text-xs text-slate-400">
                          评估时间: {new Date(assessment.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 添加目标对话框 */}
      {showAddDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-hidden">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-800">添加学习目标</h3>
              <button
                onClick={() => setShowAddDialog(false)}
                className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="p-4 space-y-4">
              {/* 目标描述 */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  目标描述 <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={newObjectiveDescription}
                  onChange={(e) => setNewObjectiveDescription(e.target.value)}
                  placeholder="例如：学生能够理解Python中的列表推导式概念并能够编写简单的列表推导式代码"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent text-sm resize-none"
                  rows={3}
                />
              </div>

              {/* 目标类型 */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  目标类型
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(['knowledge', 'skill', 'attitude'] as ObjectiveType[]).map((type) => {
                    const config = getObjectiveTypeConfig(type);
                    return (
                      <button
                        key={type}
                        onClick={() => setNewObjectiveType(type)}
                        className={`px-3 py-2 rounded-lg border-2 text-sm font-medium transition-all ${
                          newObjectiveType === type
                            ? `${config.bgColor} ${config.color} ${config.borderColor}`
                            : 'border-slate-200 text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        {config.icon} {config.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* 优先级 */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  优先级
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {(['high', 'medium', 'low'] as PriorityLevel[]).map((priority) => {
                    const config = getPriorityConfig(priority);
                    return (
                      <button
                        key={priority}
                        onClick={() => setNewObjectivePriority(priority)}
                        className={`px-3 py-2 rounded-lg border-2 text-sm font-medium transition-all ${
                          newObjectivePriority === priority
                            ? `${config.bgColor} ${config.color} ${config.borderColor}`
                            : 'border-slate-200 text-slate-600 hover:border-slate-300'
                        }`}
                      >
                        {config.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="p-4 border-t border-slate-200 flex justify-end gap-2">
              <button
                onClick={() => setShowAddDialog(false)}
                className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg text-sm font-medium transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleAddObjective}
                disabled={!newObjectiveDescription.trim()}
                className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
              >
                添加
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Default export for lazy loading
export default ObjectivesAssessmentView;
