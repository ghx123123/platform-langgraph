// QuizInterface.tsx - 知识点测验主界面
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  QuizWithQuestions,
  QuizAnswer,
  saveQuizProgress,
  loadQuizProgress,
  getQuestionTypeConfig,
  getDifficultyConfig,
  formatTime,
  submitQuiz,
} from '../../services/quizApi';
import {
  Clock,
  ChevronLeft,
  ChevronRight,
  Send,
  AlertCircle,
  Bookmark,
  BookmarkCheck,
  CheckCircle,
  HelpCircle,
} from 'lucide-react';

interface QuizInterfaceProps {
  quiz: QuizWithQuestions;
  onSubmit: (result: { quizId: string; score: number; maxScore: number }) => void;
  onExit: () => void;
}

export function QuizInterface({ quiz, onSubmit, onExit }: QuizInterfaceProps) {
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<QuizAnswer[]>([]);
  const [timeRemaining, setTimeRemaining] = useState(quiz.time_limit_minutes * 60);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [showExitConfirm, setShowExitConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number>(Date.now());

  // 初始化答案和加载进度
  useEffect(() => {
    const savedProgress = loadQuizProgress(quiz.id);
    
    if (savedProgress && !savedProgress.is_submitted) {
      setCurrentQuestionIndex(savedProgress.current_question);
      setAnswers(savedProgress.answers);
      setTimeRemaining(savedProgress.time_remaining_seconds);
    } else {
      // 初始化空答案
      const initialAnswers = quiz.questions.map(q => ({
        question_id: q.id,
        answer: q.question_type === 'multiple' ? [] : '',
        is_marked: false,
      }));
      setAnswers(initialAnswers);
    }

    startTimeRef.current = Date.now();
  }, [quiz]);

  // 倒计时
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev <= 1) {
          // 时间到，自动提交
          handleAutoSubmit();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  // 自动保存进度
  useEffect(() => {
    const saveInterval = setInterval(() => {
      if (answers.length > 0) {
        saveQuizProgress(quiz.id, {
          current_question: currentQuestionIndex,
          answers,
          time_remaining_seconds: timeRemaining,
          is_submitted: false,
        });
      }
    }, 5000); // 每5秒保存一次

    return () => clearInterval(saveInterval);
  }, [quiz.id, currentQuestionIndex, answers, timeRemaining]);

  const handleAutoSubmit = useCallback(async () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
    }
    await handleSubmit(true);
  }, [answers]);

  const currentQuestion = quiz.questions[currentQuestionIndex];
  const currentAnswer = answers.find(a => a.question_id === currentQuestion?.id);

  const handleSingleChoice = (optionId: string) => {
    setAnswers(prev =>
      prev.map(a =>
        a.question_id === currentQuestion.id
          ? { ...a, answer: optionId }
          : a
      )
    );
  };

  const handleMultipleChoice = (optionId: string) => {
    setAnswers(prev =>
      prev.map(a => {
        if (a.question_id !== currentQuestion.id) return a;
        const currentAnswers = (a.answer as string[]) || [];
        const newAnswers = currentAnswers.includes(optionId)
          ? currentAnswers.filter(id => id !== optionId)
          : [...currentAnswers, optionId];
        return { ...a, answer: newAnswers };
      })
    );
  };

  const handleFillBlank = (value: string) => {
    setAnswers(prev =>
      prev.map(a =>
        a.question_id === currentQuestion.id
          ? { ...a, answer: value }
          : a
      )
    );
  };

  const toggleMarkQuestion = () => {
    setAnswers(prev =>
      prev.map(a =>
        a.question_id === currentQuestion.id
          ? { ...a, is_marked: !a.is_marked }
          : a
      )
    );
  };

  const goToQuestion = (index: number) => {
    if (index >= 0 && index < quiz.questions.length) {
      setCurrentQuestionIndex(index);
    }
  };

  const handleNext = () => {
    goToQuestion(currentQuestionIndex + 1);
  };

  const handlePrev = () => {
    goToQuestion(currentQuestionIndex - 1);
  };

  const getAnsweredCount = () => {
    return answers.filter(a => {
      if (Array.isArray(a.answer)) {
        return a.answer.length > 0;
      }
      return a.answer !== '';
    }).length;
  };

  const getMarkedCount = () => {
    return answers.filter(a => a.is_marked).length;
  };

  const handleSubmit = async (isAutoSubmit = false) => {
    if (!isAutoSubmit) {
      const unansweredCount = quiz.questions.length - getAnsweredCount();
      if (unansweredCount > 0) {
        setShowConfirmDialog(true);
        return;
      }
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const timeSpent = Math.floor((Date.now() - startTimeRef.current) / 1000);
      const result = await submitQuiz(quiz.id, answers, timeSpent);
      
      onSubmit({
        quizId: quiz.id,
        score: result.result.total_score,
        maxScore: result.result.max_score,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败，请重试');
      setIsSubmitting(false);
    }
  };

  const isAnswered = (questionId: string) => {
    const answer = answers.find(a => a.question_id === questionId);
    if (!answer) return false;
    if (Array.isArray(answer.answer)) {
      return answer.answer.length > 0;
    }
    return answer.answer !== '';
  };

  const isMarked = (questionId: string) => {
    const answer = answers.find(a => a.question_id === questionId);
    return answer?.is_marked || false;
  };

  const timeWarning = timeRemaining < 300; // 少于5分钟警告

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-500 rounded-lg flex items-center justify-center text-white">
            <HelpCircle size={20} />
          </div>
          <div>
            <h2 className="font-bold text-slate-800">{quiz.title}</h2>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>共 {quiz.total_questions} 题</span>
              <span className="text-slate-300">|</span>
              <span>满分 {quiz.total_score} 分</span>
            </div>
          </div>
        </div>

        {/* 倒计时 */}
        <div className={`flex items-center gap-2 px-4 py-2 rounded-lg border ${
          timeWarning
            ? 'bg-red-50 border-red-200 text-red-600'
            : 'bg-slate-100 border-slate-200 text-slate-700'
        }`}>
          <Clock size={18} className={timeWarning ? 'animate-pulse' : ''} />
          <span className={`font-mono font-bold text-lg ${timeWarning ? 'animate-pulse' : ''}`}>
            {formatTime(timeRemaining)}
          </span>
        </div>

        {/* 进度概览 */}
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
            <span className="text-slate-600">已答 {getAnsweredCount()}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-amber-500"></span>
            <span className="text-slate-600">标记 {getMarkedCount()}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-slate-300"></span>
            <span className="text-slate-600">未答 {quiz.total_questions - getAnsweredCount()}</span>
          </div>
        </div>

        {/* 退出按钮 */}
        <button
          onClick={() => setShowExitConfirm(true)}
          className="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
        >
          退出
        </button>
      </div>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* 左侧题目导航栏 */}
        <div className="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-slate-200">
            <h3 className="font-semibold text-slate-700">题目导航</h3>
            <div className="mt-2 h-2 bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${((currentQuestionIndex + 1) / quiz.total_questions) * 100}%` }}
              />
            </div>
            <div className="mt-1 text-xs text-slate-500 text-center">
              {currentQuestionIndex + 1} / {quiz.total_questions}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            <div className="grid grid-cols-5 gap-2">
              {quiz.questions.map((question, index) => {
                const answered = isAnswered(question.id);
                const marked = isMarked(question.id);
                const isCurrent = index === currentQuestionIndex;

                return (
                  <button
                    key={question.id}
                    onClick={() => goToQuestion(index)}
                    className={`relative aspect-square rounded-lg font-medium text-sm transition-all ${
                      isCurrent
                        ? 'bg-indigo-500 text-white ring-2 ring-indigo-300'
                        : answered
                        ? 'bg-emerald-100 text-emerald-700 border border-emerald-300'
                        : marked
                        ? 'bg-amber-100 text-amber-700 border border-amber-300'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {index + 1}
                    {marked && (
                      <span className="absolute -top-1 -right-1 w-3 h-3 bg-amber-500 rounded-full flex items-center justify-center">
                        <span className="text-[8px] text-white">!</span>
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 图例 */}
          <div className="px-4 py-3 border-t border-slate-200 bg-slate-50">
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded bg-emerald-100 border border-emerald-300"></span>
                <span className="text-slate-600">已答</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded bg-amber-100 border border-amber-300"></span>
                <span className="text-slate-600">标记</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded bg-slate-100 border border-slate-200"></span>
                <span className="text-slate-600">未答</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded bg-indigo-500"></span>
                <span className="text-slate-600">当前</span>
              </div>
            </div>
          </div>
        </div>

        {/* 主答题区 */}
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {currentQuestion && (
            <>
              {/* 题目卡片 */}
              <div className="flex-1 overflow-y-auto p-6">
                <div className="max-w-3xl mx-auto bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                  {/* 题目头部 */}
                  <div className="px-6 py-4 bg-slate-50 border-b border-slate-200">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-lg font-bold text-slate-700">
                          第 {currentQuestionIndex + 1} 题
                        </span>
                        <span className={`px-2 py-1 rounded text-xs font-medium border ${
                          getDifficultyConfig(currentQuestion.difficulty).bgColor
                        } ${getDifficultyConfig(currentQuestion.difficulty).color} ${
                          getDifficultyConfig(currentQuestion.difficulty).borderColor
                        }`}>
                          {getDifficultyConfig(currentQuestion.difficulty).label}
                        </span>
                        <span className="px-2 py-1 rounded text-xs font-medium bg-indigo-100 text-indigo-700 border border-indigo-300">
                          {currentQuestion.score} 分
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-sm text-slate-500">
                        <span>{getQuestionTypeConfig(currentQuestion.question_type).icon}</span>
                        <span>{getQuestionTypeConfig(currentQuestion.question_type).label}</span>
                      </div>
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {getQuestionTypeConfig(currentQuestion.question_type).description}
                    </p>
                  </div>

                  {/* 题目内容 */}
                  <div className="p-6">
                    <div className="text-lg text-slate-800 leading-relaxed mb-6">
                      {currentQuestion.content}
                    </div>

                    {/* 选项区域 */}
                    {currentQuestion.question_type === 'single' && currentQuestion.options && (
                      <div className="space-y-3">
                        {currentQuestion.options.map(option => {
                          const isSelected = currentAnswer?.answer === option.id;
                          return (
                            <label
                              key={option.id}
                              className={`flex items-center gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all ${
                                isSelected
                                  ? 'bg-indigo-50 border-indigo-500'
                                  : 'bg-white border-slate-200 hover:border-slate-300'
                              }`}
                            >
                              <input
                                type="radio"
                                name={`question-${currentQuestion.id}`}
                                value={option.id}
                                checked={isSelected}
                                onChange={() => handleSingleChoice(option.id)}
                                className="sr-only"
                              />
                              <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                                isSelected
                                  ? 'border-indigo-500'
                                  : 'border-slate-300'
                              }`}>
                                {isSelected && (
                                  <div className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
                                )}
                              </div>
                              <span className="font-medium text-slate-600 min-w-[24px]">{option.label}.</span>
                              <span className="flex-1 text-slate-700">{option.content}</span>
                            </label>
                          );
                        })}
                      </div>
                    )}

                    {currentQuestion.question_type === 'multiple' && currentQuestion.options && (
                      <div className="space-y-3">
                        {currentQuestion.options.map(option => {
                          const selectedAnswers = (currentAnswer?.answer as string[]) || [];
                          const isSelected = selectedAnswers.includes(option.id);
                          return (
                            <label
                              key={option.id}
                              className={`flex items-center gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all ${
                                isSelected
                                  ? 'bg-indigo-50 border-indigo-500'
                                  : 'bg-white border-slate-200 hover:border-slate-300'
                              }`}
                            >
                              <input
                                type="checkbox"
                                value={option.id}
                                checked={isSelected}
                                onChange={() => handleMultipleChoice(option.id)}
                                className="sr-only"
                              />
                              <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                                isSelected
                                  ? 'bg-indigo-500 border-indigo-500'
                                  : 'border-slate-300'
                              }`}>
                                {isSelected && (
                                  <CheckCircle size={14} className="text-white" />
                                )}
                              </div>
                              <span className="font-medium text-slate-600 min-w-[24px]">{option.label}.</span>
                              <span className="flex-1 text-slate-700">{option.content}</span>
                            </label>
                          );
                        })}
                      </div>
                    )}

                    {currentQuestion.question_type === 'fill_blank' && (
                      <div className="space-y-3">
                        <input
                          type="text"
                          value={(currentAnswer?.answer as string) || ''}
                          onChange={(e) => handleFillBlank(e.target.value)}
                          placeholder="请输入答案..."
                          className="w-full px-4 py-3 border-2 border-slate-200 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition-all text-slate-700"
                        />
                      </div>
                    )}

                    {currentQuestion.question_type === 'short_answer' && (
                      <div className="space-y-3">
                        <textarea
                          value={(currentAnswer?.answer as string) || ''}
                          onChange={(e) => handleFillBlank(e.target.value)}
                          placeholder="请简要回答..."
                          rows={6}
                          className="w-full px-4 py-3 border-2 border-slate-200 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition-all text-slate-700 resize-none"
                        />
                        <p className="text-xs text-slate-500 text-right">
                          已输入 {((currentAnswer?.answer as string) || '').length} 字
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* 底部操作栏 */}
              <div className="px-6 py-4 bg-white border-t border-slate-200 shrink-0">
                <div className="flex items-center justify-between max-w-3xl mx-auto">
                  <button
                    onClick={handlePrev}
                    disabled={currentQuestionIndex === 0}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <ChevronLeft size={18} />
                    <span>上一题</span>
                  </button>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={toggleMarkQuestion}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                        currentAnswer?.is_marked
                          ? 'bg-amber-100 text-amber-700 border border-amber-300'
                          : 'bg-slate-100 text-slate-600 border border-slate-200 hover:bg-slate-200'
                      }`}
                    >
                      {currentAnswer?.is_marked ? (
                        <>
                          <BookmarkCheck size={18} />
                          <span>已标记</span>
                        </>
                      ) : (
                        <>
                          <Bookmark size={18} />
                          <span>标记</span>
                        </>
                      )}
                    </button>
                  </div>

                  {currentQuestionIndex === quiz.questions.length - 1 ? (
                    <button
                      onClick={() => handleSubmit()}
                      disabled={isSubmitting}
                      className="flex items-center gap-2 px-6 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                    >
                      {isSubmitting ? (
                        <>
                          <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          <span>提交中...</span>
                        </>
                      ) : (
                        <>
                          <Send size={18} />
                          <span>提交</span>
                        </>
                      )}
                    </button>
                  ) : (
                    <button
                      onClick={handleNext}
                      className="flex items-center gap-2 px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg transition-colors"
                    >
                      <span>下一题</span>
                      <ChevronRight size={18} />
                    </button>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 提交确认对话框 */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-md w-full mx-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
                <AlertCircle className="text-amber-600" size={20} />
              </div>
              <h3 className="text-lg font-bold text-slate-800">确认提交?</h3>
            </div>
            
            <div className="mb-6 space-y-2 text-sm text-slate-600">
              <p>
                你还有 <strong className="text-amber-600">{quiz.total_questions - getAnsweredCount()}</strong> 道题未作答。
              </p>
              <p>提交后将无法修改答案，是否继续?</p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirmDialog(false)}
                className="flex-1 px-4 py-2 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 transition-colors"
              >
                继续答题
              </button>
              <button
                onClick={() => {
                  setShowConfirmDialog(false);
                  handleSubmit(true);
                }}
                disabled={isSubmitting}
                className="flex-1 px-4 py-2 bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 transition-colors disabled:opacity-50"
              >
                {isSubmitting ? '提交中...' : '确认提交'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 退出确认对话框 */}
      {showExitConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-md w-full mx-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                <AlertCircle className="text-red-600" size={20} />
              </div>
              <h3 className="text-lg font-bold text-slate-800">确认退出?</h3>
            </div>
            
            <div className="mb-6 text-sm text-slate-600">
              <p>退出后答题进度将被保存，你可以稍后继续作答。</p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowExitConfirm(false)}
                className="flex-1 px-4 py-2 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 transition-colors"
              >
                继续答题
              </button>
              <button
                onClick={() => {
                  saveQuizProgress(quiz.id, {
                    current_question: currentQuestionIndex,
                    answers,
                    time_remaining_seconds: timeRemaining,
                    is_submitted: false,
                  });
                  setShowExitConfirm(false);
                  onExit();
                }}
                className="flex-1 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
              >
                确认退出
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-50">
          <div className="px-6 py-3 bg-red-500 text-white rounded-lg shadow-lg flex items-center gap-3">
            <AlertCircle size={18} />
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-2 text-white/70 hover:text-white"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* 时间警告遮罩 */}
      {timeWarning && timeRemaining <= 60 && (
        <div className="fixed top-4 right-4 z-50">
          <div className="px-4 py-3 bg-red-500 text-white rounded-lg shadow-lg animate-pulse">
            <div className="flex items-center gap-2">
              <Clock size={18} />
              <span className="font-bold">时间紧迫！</span>
            </div>
            <p className="text-sm mt-1">剩余时间: {formatTime(timeRemaining)}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default QuizInterface;
