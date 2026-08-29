// quizApi.ts - 知识点测验 API 服务

export type QuestionType = 'single' | 'multiple' | 'fill_blank' | 'short_answer';
export type QuizStatus = 'draft' | 'active' | 'completed' | 'expired';

export interface QuizQuestion {
  id: string;
  quiz_id: string;
  question_number: number;
  question_type: QuestionType;
  content: string;
  options?: QuizOption[];
  correct_answer?: string | string[];
  explanation?: string;
  knowledge_point: string;
  difficulty: 'easy' | 'medium' | 'hard';
  score: number;
}

export interface QuizOption {
  id: string;
  label: string;
  content: string;
}

export interface Quiz {
  id: string;
  session_id: string;
  title: string;
  description?: string;
  status: QuizStatus;
  total_questions: number;
  total_score: number;
  time_limit_minutes: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface QuizWithQuestions extends Quiz {
  questions: QuizQuestion[];
}

export interface QuizAnswer {
  question_id: string;
  answer: string | string[];
  is_marked?: boolean;
}

export interface QuizSubmission {
  quiz_id: string;
  answers: QuizAnswer[];
  time_spent_seconds: number;
  submitted_at: string;
}

export interface QuestionResult {
  question_id: string;
  question_number: number;
  is_correct: boolean;
  score: number;
  max_score: number;
  user_answer: string | string[];
  correct_answer: string | string[];
  explanation?: string;
}

export interface WeakKnowledgePoint {
  knowledge_point: string;
  total_questions: number;
  correct_count: number;
  accuracy_rate: number;
}

export interface QuizResult {
  quiz_id: string;
  total_score: number;
  max_score: number;
  score_percentage: number;
  passed: boolean;
  time_spent_seconds: number;
  question_results: QuestionResult[];
  weak_points: WeakKnowledgePoint[];
  suggestions: string[];
  completed_at: string;
}

export interface GenerateQuizOptions {
  question_count?: number;
  time_limit_minutes?: number;
  difficulty_distribution?: {
    easy?: number;
    medium?: number;
    hard?: number;
  };
  question_types?: QuestionType[];
  focus_knowledge_points?: string[];
}

export interface QuizProgress {
  current_question: number;
  answers: QuizAnswer[];
  time_remaining_seconds: number;
  is_submitted: boolean;
}

const STORAGE_KEY_PREFIX = 'quiz_progress_';

/**
 * 获取测验详情
 * @param quizId 测验ID
 * @returns 测验详情（包含题目）
 */
export async function fetchQuiz(quizId: string): Promise<QuizWithQuestions> {
  try {
    const response = await fetch(`/api/quizzes/${quizId}`);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('测验不存在');
      }
      throw new Error(`获取测验详情失败: ${response.status}`);
    }

    const data = await response.json();
    return data.quiz;
  } catch (error) {
    console.error('[QuizApi] 获取测验详情失败:', error);
    throw error instanceof Error ? error : new Error('获取测验详情失败');
  }
}

/**
 * 生成测验
 * @param sessionId 教学会话ID
 * @param options 生成选项
 * @returns 生成的测验
 */
export async function generateQuiz(
  sessionId: string,
  options?: GenerateQuizOptions
): Promise<QuizWithQuestions> {
  try {
    const response = await fetch(`/api/teaching/sessions/${sessionId}/quizzes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question_count: options?.question_count || 10,
        time_limit_minutes: options?.time_limit_minutes || 30,
        difficulty_distribution: options?.difficulty_distribution || {
          easy: 0.3,
          medium: 0.5,
          hard: 0.2,
        },
        question_types: options?.question_types || ['single', 'multiple', 'fill_blank', 'short_answer'],
        focus_knowledge_points: options?.focus_knowledge_points || [],
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `生成测验失败: ${response.status}`);
    }

    const data = await response.json();
    return data.quiz;
  } catch (error) {
    console.error('[QuizApi] 生成测验失败:', error);
    throw error instanceof Error ? error : new Error('生成测验失败');
  }
}

/**
 * 提交测验答案
 * @param quizId 测验ID
 * @param answers 答案列表
 * @returns 提交结果
 */
export async function submitQuiz(
  quizId: string,
  answers: QuizAnswer[],
  timeSpentSeconds: number
): Promise<{ result: QuizResult }> {
  try {
    const response = await fetch(`/api/quizzes/${quizId}/submit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        answers,
        time_spent_seconds: timeSpentSeconds,
        submitted_at: new Date().toISOString(),
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `提交测验失败: ${response.status}`);
    }

    const data = await response.json();
    
    // 清除本地存储的进度
    clearQuizProgress(quizId);
    
    return data;
  } catch (error) {
    console.error('[QuizApi] 提交测验失败:', error);
    throw error instanceof Error ? error : new Error('提交测验失败');
  }
}

/**
 * 获取测验结果
 * @param quizId 测验ID
 * @returns 测验结果
 */
export async function fetchQuizResults(quizId: string): Promise<QuizResult> {
  try {
    const response = await fetch(`/api/quizzes/${quizId}/results`);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('测验结果不存在');
      }
      throw new Error(`获取测验结果失败: ${response.status}`);
    }

    const data = await response.json();
    return data.result;
  } catch (error) {
    console.error('[QuizApi] 获取测验结果失败:', error);
    throw error instanceof Error ? error : new Error('获取测验结果失败');
  }
}

/**
 * 开始测验
 * @param quizId 测验ID
 * @returns 更新后的测验
 */
export async function startQuiz(quizId: string): Promise<Quiz> {
  try {
    const response = await fetch(`/api/quizzes/${quizId}/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `开始测验失败: ${response.status}`);
    }

    const data = await response.json();
    return data.quiz;
  } catch (error) {
    console.error('[QuizApi] 开始测验失败:', error);
    throw error instanceof Error ? error : new Error('开始测验失败');
  }
}

/**
 * 保存测验进度到本地存储
 * @param quizId 测验ID
 * @param progress 进度数据
 */
export function saveQuizProgress(quizId: string, progress: QuizProgress): void {
  try {
    const key = `${STORAGE_KEY_PREFIX}${quizId}`;
    localStorage.setItem(key, JSON.stringify(progress));
  } catch (error) {
    console.error('[QuizApi] 保存进度失败:', error);
  }
}

/**
 * 从本地存储加载测验进度
 * @param quizId 测验ID
 * @returns 进度数据或null
 */
export function loadQuizProgress(quizId: string): QuizProgress | null {
  try {
    const key = `${STORAGE_KEY_PREFIX}${quizId}`;
    const data = localStorage.getItem(key);
    return data ? JSON.parse(data) : null;
  } catch (error) {
    console.error('[QuizApi] 加载进度失败:', error);
    return null;
  }
}

/**
 * 清除本地存储的测验进度
 * @param quizId 测验ID
 */
export function clearQuizProgress(quizId: string): void {
  try {
    const key = `${STORAGE_KEY_PREFIX}${quizId}`;
    localStorage.removeItem(key);
  } catch (error) {
    console.error('[QuizApi] 清除进度失败:', error);
  }
}

/**
 * 获取题目类型配置
 * @param type 题目类型
 * @returns 类型配置对象
 */
export function getQuestionTypeConfig(type: QuestionType): {
  label: string;
  icon: string;
  description: string;
} {
  switch (type) {
    case 'single':
      return {
        label: '单选题',
        icon: '◉',
        description: '请选择唯一正确答案',
      };
    case 'multiple':
      return {
        label: '多选题',
        icon: '☑',
        description: '请选择所有正确答案',
      };
    case 'fill_blank':
      return {
        label: '填空题',
        icon: '✎',
        description: '请填写正确答案',
      };
    case 'short_answer':
      return {
        label: '简答题',
        icon: '✍',
        description: '请简要回答',
      };
    default:
      return {
        label: '未知题型',
        icon: '?',
        description: '未知题型',
      };
  }
}

/**
 * 获取难度配置
 * @param difficulty 难度等级
 * @returns 难度配置对象
 */
export function getDifficultyConfig(difficulty: 'easy' | 'medium' | 'hard'): {
  label: string;
  color: string;
  bgColor: string;
  borderColor: string;
} {
  switch (difficulty) {
    case 'easy':
      return {
        label: '简单',
        color: 'text-emerald-600',
        bgColor: 'bg-emerald-100',
        borderColor: 'border-emerald-300',
      };
    case 'medium':
      return {
        label: '中等',
        color: 'text-amber-600',
        bgColor: 'bg-amber-100',
        borderColor: 'border-amber-300',
      };
    case 'hard':
      return {
        label: '困难',
        color: 'text-red-600',
        bgColor: 'bg-red-100',
        borderColor: 'border-red-300',
      };
    default:
      return {
        label: '未知',
        color: 'text-slate-600',
        bgColor: 'bg-slate-100',
        borderColor: 'border-slate-300',
      };
  }
}

/**
 * 获取成绩等级配置
 * @param percentage 分数百分比
 * @returns 等级配置对象
 */
export function getScoreLevelConfig(percentage: number): {
  level: string;
  color: string;
  bgColor: string;
  message: string;
} {
  if (percentage >= 90) {
    return {
      level: '优秀',
      color: 'text-emerald-600',
      bgColor: 'bg-emerald-500',
      message: '太棒了！你已经很好地掌握了这些知识！',
    };
  } else if (percentage >= 80) {
    return {
      level: '良好',
      color: 'text-blue-600',
      bgColor: 'bg-blue-500',
      message: '表现不错！继续保持！',
    };
  } else if (percentage >= 60) {
    return {
      level: '及格',
      color: 'text-amber-600',
      bgColor: 'bg-amber-500',
      message: '刚好及格，还有提升空间哦！',
    };
  } else {
    return {
      level: '需努力',
      color: 'text-red-600',
      bgColor: 'bg-red-500',
      message: '别灰心，建议重新学习相关知识点！',
    };
  }
}

/**
 * 格式化时间（秒 -> mm:ss）
 * @param seconds 秒数
 * @returns 格式化后的时间字符串
 */
export function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
}

export default {
  fetchQuiz,
  generateQuiz,
  submitQuiz,
  fetchQuizResults,
  startQuiz,
  saveQuizProgress,
  loadQuizProgress,
  clearQuizProgress,
  getQuestionTypeConfig,
  getDifficultyConfig,
  getScoreLevelConfig,
  formatTime,
};
