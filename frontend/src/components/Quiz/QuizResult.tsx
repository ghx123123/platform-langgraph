// QuizResult.tsx - 测验结果展示
import { useState } from 'react';
import {
  QuizResult as QuizResultType,
  QuizWithQuestions,
  getScoreLevelConfig,
  getQuestionTypeConfig,
  getDifficultyConfig,
  formatTime,
} from '../../services/quizApi';
import {
  Trophy,
  Clock,
  Target,
  AlertCircle,
  CheckCircle,
  XCircle,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  BookOpen,
  Lightbulb,
  TrendingUp,
  Award,
  BarChart3,
} from 'lucide-react';

interface QuizResultProps {
  result: QuizResultType;
  quiz: QuizWithQuestions;
  onRetry: () => void;
  onBack: () => void;
  onReviewKnowledge?: (knowledgePoint: string) => void;
}

export function QuizResult({ result, quiz, onRetry, onBack, onReviewKnowledge }: QuizResultProps) {
  const [expandedQuestions, setExpandedQuestions] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState<'overview' | 'details' | 'weak'>('overview');

  const scoreConfig = getScoreLevelConfig(result.score_percentage);
  const passed = result.passed;

  const toggleQuestion = (questionId: string) => {
    setExpandedQuestions(prev => {
      const newSet = new Set(prev);
      if (newSet.has(questionId)) {
        newSet.delete(questionId);
      } else {
        newSet.add(questionId);
      }
      return newSet;
    });
  };

  const getQuestionById = (questionId: string) => {
    return quiz.questions.find(q => q.id === questionId);
  };

  const correctCount = result.question_results.filter(r => r.is_correct).length;
  const wrongCount = result.question_results.length - correctCount;
  const accuracy = Math.round((correctCount / result.question_results.length) * 100);

  return (
    <div className="flex flex-col h-full bg-slate-50 overflow-hidden">
      {/* 顶部标题栏 */}
      <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-emerald-500 rounded-lg flex items-center justify-center text-white">
            <Trophy size={20} />
          </div>
          <div>
            <h2 className="font-bold text-slate-800">测验结果</h2>
            <p className="text-xs text-slate-500">{quiz.title}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onRetry}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg transition-colors"
          >
            <RotateCcw size={18} />
            <span>再测一次</span>
          </button>
          <button
            onClick={onBack}
            className="px-4 py-2 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 transition-colors"
          >
            返回
          </button>
        </div>
      </div>

      {/* 标签页导航 */}
      <div className="flex items-center gap-1 px-6 py-2 bg-white border-b border-slate-200 shrink-0">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            activeTab === 'overview'
              ? 'bg-indigo-100 text-indigo-700'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <span className="flex items-center gap-2">
            <BarChart3 size={16} />
            总览
          </span>
        </button>
        <button
          onClick={() => setActiveTab('details')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            activeTab === 'details'
              ? 'bg-indigo-100 text-indigo-700'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <span className="flex items-center gap-2">
            <BookOpen size={16} />
            答题详情
          </span>
        </button>
        <button
          onClick={() => setActiveTab('weak')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            activeTab === 'weak'
              ? 'bg-indigo-100 text-indigo-700'
              : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          <span className="flex items-center gap-2">
            <Target size={16} />
            薄弱知识点
          </span>
        </button>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto">
          {/* 总览标签页 */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* 成绩卡片 */}
              <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="p-6 text-center">
                  {/* 分数环形图 */}
                  <div className="relative inline-flex items-center justify-center mb-4">
                    <svg className="w-32 h-32 transform -rotate-90">
                      <circle
                        cx="64"
                        cy="64"
                        r="56"
                        fill="none"
                        stroke="#e2e8f0"
                        strokeWidth="12"
                      />
                      <circle
                        cx="64"
                        cy="64"
                        r="56"
                        fill="none"
                        stroke={passed ? '#10b981' : '#ef4444'}
                        strokeWidth="12"
                        strokeLinecap="round"
                        strokeDasharray={`${(result.score_percentage / 100) * 351.86} 351.86`}
                        className="transition-all duration-1000"
                      />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-3xl font-bold ${scoreConfig.color}`}>
                        {result.score_percentage}
                      </span>
                      <span className="text-sm text-slate-500">分</span>
                    </div>
                  </div>

                  <h3 className={`text-2xl font-bold ${scoreConfig.color} mb-2`}>
                    {scoreConfig.level}
                  </h3>
                  <p className="text-slate-600 mb-4">{scoreConfig.message}</p>

                  <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full ${
                    passed ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                  }`}>
                    {passed ? (
                      <>
                        <CheckCircle size={18} />
                        <span className="font-medium">通过测验</span>
                      </>
                    ) : (
                      <>
                        <XCircle size={18} />
                        <span className="font-medium">未通过</span>
                      </>
                    )}
                  </div>
                </div>

                {/* 统计信息 */}
                <div className="grid grid-cols-4 divide-x divide-slate-200 border-t border-slate-200">
                  <div className="p-4 text-center">
                    <div className="flex items-center justify-center gap-1 text-slate-500 mb-1">
                      <Award size={16} />
                      <span className="text-xs">得分</span>
                    </div>
                    <div className="text-xl font-bold text-slate-800">
                      {result.total_score}<span className="text-sm text-slate-400">/{result.max_score}</span>
                    </div>
                  </div>
                  <div className="p-4 text-center">
                    <div className="flex items-center justify-center gap-1 text-slate-500 mb-1">
                      <Target size={16} />
                      <span className="text-xs">正确率</span>
                    </div>
                    <div className={`text-xl font-bold ${accuracy >= 60 ? 'text-emerald-600' : 'text-red-600'}`}>
                      {accuracy}%
                    </div>
                  </div>
                  <div className="p-4 text-center">
                    <div className="flex items-center justify-center gap-1 text-slate-500 mb-1">
                      <Clock size={16} />
                      <span className="text-xs">用时</span>
                    </div>
                    <div className="text-xl font-bold text-slate-800">
                      {formatTime(result.time_spent_seconds)}
                    </div>
                  </div>
                  <div className="p-4 text-center">
                    <div className="flex items-center justify-center gap-1 text-slate-500 mb-1">
                      <TrendingUp size={16} />
                      <span className="text-xs">排名</span>
                    </div>
                    <div className="text-xl font-bold text-slate-800">-</div>
                  </div>
                </div>
              </div>

              {/* 答题统计 */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white rounded-xl p-4 border border-slate-200">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-emerald-100 rounded-lg flex items-center justify-center">
                      <CheckCircle className="text-emerald-600" size={24} />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-emerald-600">{correctCount}</div>
                      <div className="text-sm text-slate-500">正确</div>
                    </div>
                  </div>
                </div>
                <div className="bg-white rounded-xl p-4 border border-slate-200">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center">
                      <XCircle className="text-red-600" size={24} />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-red-600">{wrongCount}</div>
                      <div className="text-sm text-slate-500">错误</div>
                    </div>
                  </div>
                </div>
                <div className="bg-white rounded-xl p-4 border border-slate-200">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center">
                      <HelpCircle className="text-indigo-600" size={24} />
                    </div>
                    <div>
                      <div className="text-2xl font-bold text-indigo-600">{result.question_results.length}</div>
                      <div className="text-sm text-slate-500">总题数</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 改进建议 */}
              {result.suggestions && result.suggestions.length > 0 && (
                <div className="bg-white rounded-xl p-6 border border-slate-200">
                  <div className="flex items-center gap-2 mb-4">
                    <Lightbulb className="text-amber-500" size={20} />
                    <h3 className="font-bold text-slate-800">改进建议</h3>
                  </div>
                  <ul className="space-y-3">
                    {result.suggestions.map((suggestion, index) => (
                      <li key={index} className="flex items-start gap-3">
                        <span className="flex-shrink-0 w-6 h-6 bg-amber-100 text-amber-700 rounded-full flex items-center justify-center text-sm font-medium">
                          {index + 1}
                        </span>
                        <p className="text-slate-700 text-sm leading-relaxed">{suggestion}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* 答题详情标签页 */}
          {activeTab === 'details' && (
            <div className="space-y-4">
              {result.question_results.map((questionResult, index) => {
                const question = getQuestionById(questionResult.question_id);
                if (!question) return null;

                const isExpanded = expandedQuestions.has(questionResult.question_id);
                const typeConfig = getQuestionTypeConfig(question.question_type);
                const difficultyConfig = getDifficultyConfig(question.difficulty);

                return (
                  <div
                    key={questionResult.question_id}
                    className={`bg-white rounded-xl border-2 overflow-hidden transition-all ${
                      questionResult.is_correct
                        ? 'border-emerald-200'
                        : 'border-red-200'
                    }`}
                  >
                    {/* 题目头部 */}
                    <button
                      onClick={() => toggleQuestion(questionResult.question_id)}
                      className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-center gap-4">
                        <span className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
                          questionResult.is_correct
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-red-100 text-red-700'
                        }`}>
                          {index + 1}
                        </span>
                        <div className="text-left">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm text-slate-500">{typeConfig.label}</span>
                            <span className={`text-xs px-2 py-0.5 rounded border ${difficultyConfig.bgColor} ${difficultyConfig.color} ${difficultyConfig.borderColor}`}>
                              {difficultyConfig.label}
                            </span>
                          </div>
                          <p className="text-slate-700 text-sm line-clamp-1">{question.content}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <span className={`font-bold ${
                          questionResult.is_correct ? 'text-emerald-600' : 'text-red-600'
                        }`}>
                          {questionResult.score}/{questionResult.max_score}分
                        </span>
                        {questionResult.is_correct ? (
                          <CheckCircle className="text-emerald-500" size={20} />
                        ) : (
                          <XCircle className="text-red-500" size={20} />
                        )}
                        {isExpanded ? (
                          <ChevronUp className="text-slate-400" size={20} />
                        ) : (
                          <ChevronDown className="text-slate-400" size={20} />
                        )}
                      </div>
                    </button>

                    {/* 展开详情 */}
                    {isExpanded && (
                      <div className="px-6 pb-6 border-t border-slate-100">
                        {/* 题目完整内容 */}
                        <div className="py-4">
                          <p className="text-slate-800">{question.content}</p>
                        </div>

                        {/* 选项 */}
                        {question.options && (
                          <div className="space-y-2 mb-4">
                            {question.options.map(option => {
                              const isUserAnswer = Array.isArray(questionResult.user_answer)
                                ? questionResult.user_answer.includes(option.id)
                                : questionResult.user_answer === option.id;
                              const isCorrectAnswer = Array.isArray(questionResult.correct_answer)
                                ? questionResult.correct_answer.includes(option.id)
                                : questionResult.correct_answer === option.id;

                              let optionClass = 'border-slate-200 bg-white';
                              if (isCorrectAnswer) {
                                optionClass = 'border-emerald-500 bg-emerald-50';
                              } else if (isUserAnswer && !isCorrectAnswer) {
                                optionClass = 'border-red-500 bg-red-50';
                              }

                              return (
                                <div
                                  key={option.id}
                                  className={`flex items-center gap-3 p-3 rounded-lg border-2 ${optionClass}`}
                                >
                                  <span className="font-medium text-slate-600 min-w-[24px]">{option.label}.</span>
                                  <span className="flex-1 text-slate-700">{option.content}</span>
                                  {isCorrectAnswer && (
                                    <CheckCircle className="text-emerald-500" size={18} />
                                  )}
                                  {isUserAnswer && !isCorrectAnswer && (
                                    <XCircle className="text-red-500" size={18} />
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* 填空/简答题答案 */}
                        {(question.question_type === 'fill_blank' || question.question_type === 'short_answer') && (
                          <div className="space-y-3 mb-4">
                            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                              <div className="text-xs text-red-600 mb-1">你的答案</div>
                              <div className="text-slate-700">
                                {Array.isArray(questionResult.user_answer)
                                  ? questionResult.user_answer.join(', ')
                                  : questionResult.user_answer || '（未作答）'}
                              </div>
                            </div>
                            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                              <div className="text-xs text-emerald-600 mb-1">正确答案</div>
                              <div className="text-slate-700">
                                {Array.isArray(questionResult.correct_answer)
                                  ? questionResult.correct_answer.join(', ')
                                  : questionResult.correct_answer}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* 答案解析 */}
                        {questionResult.explanation && (
                          <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                            <div className="flex items-center gap-2 mb-2">
                              <Lightbulb className="text-blue-500" size={16} />
                              <span className="font-medium text-blue-700">答案解析</span>
                            </div>
                            <p className="text-slate-700 text-sm">{questionResult.explanation}</p>
                          </div>
                        )}

                        {/* 知识点标签 */}
                        <div className="mt-4 flex items-center gap-2">
                          <span className="text-xs text-slate-500">知识点:</span>
                          <span className="px-2 py-1 bg-indigo-100 text-indigo-700 text-xs rounded">
                            {question.knowledge_point}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* 薄弱知识点标签页 */}
          {activeTab === 'weak' && (
            <div className="space-y-6">
              {result.weak_points && result.weak_points.length > 0 ? (
                <>
                  {/* 薄弱点列表 */}
                  <div className="space-y-4">
                    {result.weak_points.map((point, index) => (
                      <div key={index} className="bg-white rounded-xl p-6 border border-slate-200">
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-3">
                            <span className="w-8 h-8 bg-red-100 text-red-700 rounded-full flex items-center justify-center font-bold">
                              {index + 1}
                            </span>
                            <h3 className="font-bold text-slate-800">{point.knowledge_point}</h3>
                          </div>
                          {onReviewKnowledge && (
                            <button
                              onClick={() => onReviewKnowledge(point.knowledge_point)}
                              className="flex items-center gap-2 px-3 py-1.5 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                            >
                              <BookOpen size={16} />
                              复习
                            </button>
                          )}
                        </div>

                        {/* 正确率进度条 */}
                        <div className="mb-4">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm text-slate-500">掌握程度</span>
                            <span className={`text-sm font-bold ${
                              point.accuracy_rate >= 60 ? 'text-emerald-600' : 'text-red-600'
                            }`}>
                              {point.accuracy_rate}%
                            </span>
                          </div>
                          <div className="h-3 bg-slate-200 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                point.accuracy_rate >= 60 ? 'bg-emerald-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${point.accuracy_rate}%` }}
                            />
                          </div>
                        </div>

                        <div className="flex items-center gap-6 text-sm text-slate-600">
                          <span>共 {point.total_questions} 题</span>
                          <span className="text-emerald-600">正确 {point.correct_count} 题</span>
                          <span className="text-red-600">错误 {point.total_questions - point.correct_count} 题</span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* 建议 */}
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-6">
                    <div className="flex items-center gap-2 mb-3">
                      <AlertCircle className="text-amber-600" size={20} />
                      <h3 className="font-bold text-amber-800">学习建议</h3>
                    </div>
                    <ul className="space-y-2 text-sm text-amber-700">
                      <li>• 针对薄弱知识点，建议重新学习相关课程内容</li>
                      <li>• 多练习相关类型的题目，加深理解</li>
                      <li>• 可以参加讨论或向老师请教疑难问题</li>
                      <li>• 建议收藏错题，定期复习</li>
                    </ul>
                  </div>
                </>
              ) : (
                <div className="bg-white rounded-xl p-12 border border-slate-200 text-center">
                  <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Trophy className="text-emerald-500" size={32} />
                  </div>
                  <h3 className="text-lg font-bold text-slate-800 mb-2">恭喜你！</h3>
                  <p className="text-slate-600">你掌握得很好，没有发现薄弱知识点。</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default QuizResult;
