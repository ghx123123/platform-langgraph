// objectivesApi.ts - 学习目标与匹配度评估 API 服务

export type ObjectiveType = 'knowledge' | 'skill' | 'attitude';
export type PriorityLevel = 'high' | 'medium' | 'low';

export interface LearningObjective {
  id: string;
  session_id: string;
  description: string;
  objective_type: ObjectiveType;
  priority: PriorityLevel;
  related_knowledge_points: string[];
  created_at: string;
}

export interface ObjectiveAssessment {
  id: string;
  session_id: string;
  objective_id: string;
  coverage_score: number;
  evidence: string;
  gaps: string[];
  suggestions: string[];
  created_at: string;
}

export interface AssessmentSummary {
  avg_score: number;
  total_objectives: number;
  assessed_count: number;
  covered_count: number;
  uncovered_count: number;
}

export interface AssessmentData {
  objective_assessments: ObjectiveAssessment[];
  summary: AssessmentSummary;
}

export interface CreateObjectiveRequest {
  description: string;
  objective_type?: ObjectiveType;
  priority?: PriorityLevel;
  related_knowledge_points?: string[];
}

/**
 * 获取学习目标列表
 * @param sessionId 教学会话ID
 * @returns 学习目标列表
 */
export async function fetchObjectives(sessionId: string): Promise<LearningObjective[]> {
  try {
    const response = await fetch(`/api/teaching/sessions/${sessionId}/objectives`);

    if (!response.ok) {
      if (response.status === 404) {
        return [];
      }
      throw new Error(`获取学习目标失败: ${response.status}`);
    }

    const data = await response.json();
    return data.objectives || [];
  } catch (error) {
    console.error('[ObjectivesApi] 获取学习目标失败:', error);
    throw error instanceof Error ? error : new Error('获取学习目标失败');
  }
}

/**
 * 获取匹配度评估结果
 * @param sessionId 教学会话ID
 * @returns 评估结果和汇总统计
 */
export async function fetchObjectiveAssessment(sessionId: string): Promise<AssessmentData> {
  try {
    const response = await fetch(`/api/teaching/sessions/${sessionId}/objective-assessment`);

    if (!response.ok) {
      if (response.status === 404) {
        return {
          objective_assessments: [],
          summary: {
            avg_score: 0,
            total_objectives: 0,
            assessed_count: 0,
            covered_count: 0,
            uncovered_count: 0,
          },
        };
      }
      throw new Error(`获取匹配度评估失败: ${response.status}`);
    }

    const data = await response.json();
    return {
      objective_assessments: data.objective_assessments || [],
      summary: data.summary || {
        avg_score: 0,
        total_objectives: 0,
        assessed_count: 0,
        covered_count: 0,
        uncovered_count: 0,
      },
    };
  } catch (error) {
    console.error('[ObjectivesApi] 获取匹配度评估失败:', error);
    throw error instanceof Error ? error : new Error('获取匹配度评估失败');
  }
}

/**
 * 创建学习目标
 * @param sessionId 教学会话ID
 * @param data 学习目标数据
 * @returns 创建的学习目标
 */
export async function createObjective(
  sessionId: string,
  data: CreateObjectiveRequest
): Promise<LearningObjective> {
  try {
    const response = await fetch(`/api/teaching/sessions/${sessionId}/objectives`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        description: data.description,
        objective_type: data.objective_type || 'knowledge',
        priority: data.priority || 'medium',
        related_knowledge_points: data.related_knowledge_points || [],
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `创建学习目标失败: ${response.status}`);
    }

    const result = await response.json();
    return result.objective;
  } catch (error) {
    console.error('[ObjectivesApi] 创建学习目标失败:', error);
    throw error instanceof Error ? error : new Error('创建学习目标失败');
  }
}

/**
 * 删除学习目标
 * @param sessionId 教学会话ID
 * @param objectiveId 学习目标ID
 * @returns 是否删除成功
 */
export async function deleteObjective(
  sessionId: string,
  objectiveId: string
): Promise<boolean> {
  try {
    const response = await fetch(
      `/api/teaching/sessions/${sessionId}/objectives/${objectiveId}`,
      {
        method: 'DELETE',
      }
    );

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('学习目标不存在');
      }
      throw new Error(`删除学习目标失败: ${response.status}`);
    }

    return true;
  } catch (error) {
    console.error('[ObjectivesApi] 删除学习目标失败:', error);
    throw error instanceof Error ? error : new Error('删除学习目标失败');
  }
}

/**
 * 触发匹配度分析
 * @param sessionId 教学会话ID
 * @param objectiveId 可选，指定要评估的目标ID
 * @returns 评估结果
 */
export async function triggerAssessment(
  sessionId: string,
  objectiveId?: string
): Promise<AssessmentData> {
  try {
    const url = objectiveId
      ? `/api/teaching/sessions/${sessionId}/objective-assessment?objective_id=${objectiveId}`
      : `/api/teaching/sessions/${sessionId}/objective-assessment`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `触发匹配度分析失败: ${response.status}`);
    }

    const data = await response.json();

    // 如果评估的是单个目标
    if (objectiveId && data.assessment) {
      return {
        objective_assessments: [data.assessment],
        summary: {
          avg_score: data.assessment.coverage_score,
          total_objectives: 1,
          assessed_count: 1,
          covered_count: data.assessment.coverage_score >= 70 ? 1 : 0,
          uncovered_count: data.assessment.coverage_score >= 70 ? 0 : 1,
        },
      };
    }

    // 评估所有目标
    return {
      objective_assessments: data.assessments || [],
      summary: data.summary || {
        avg_score: 0,
        total_objectives: 0,
        assessed_count: 0,
        covered_count: 0,
        uncovered_count: 0,
      },
    };
  } catch (error) {
    console.error('[ObjectivesApi] 触发匹配度分析失败:', error);
    throw error instanceof Error ? error : new Error('触发匹配度分析失败');
  }
}

/**
 * 获取匹配度颜色配置
 * @param score 匹配度分数 (0-100)
 * @returns 颜色配置对象
 */
export function getMatchLevelConfig(score: number): {
  color: string;
  bgColor: string;
  borderColor: string;
  lightBg: string;
  label: string;
  icon: string;
} {
  if (score >= 80) {
    return {
      color: 'text-emerald-600',
      bgColor: 'bg-emerald-500',
      borderColor: 'border-emerald-300',
      lightBg: 'bg-emerald-50',
      label: '高匹配',
      icon: '✓',
    };
  } else if (score >= 50) {
    return {
      color: 'text-amber-600',
      bgColor: 'bg-amber-500',
      borderColor: 'border-amber-300',
      lightBg: 'bg-amber-50',
      label: '中匹配',
      icon: '~',
    };
  } else {
    return {
      color: 'text-red-600',
      bgColor: 'bg-red-500',
      borderColor: 'border-red-300',
      lightBg: 'bg-red-50',
      label: '低匹配',
      icon: '✕',
    };
  }
}

/**
 * 获取目标类型配置
 * @param type 目标类型
 * @returns 类型配置对象
 */
export function getObjectiveTypeConfig(type: ObjectiveType): {
  color: string;
  bgColor: string;
  borderColor: string;
  label: string;
  icon: string;
} {
  switch (type) {
    case 'knowledge':
      return {
        color: 'text-blue-600',
        bgColor: 'bg-blue-100',
        borderColor: 'border-blue-300',
        label: '知识',
        icon: '📚',
      };
    case 'skill':
      return {
        color: 'text-purple-600',
        bgColor: 'bg-purple-100',
        borderColor: 'border-purple-300',
        label: '技能',
        icon: '🛠️',
      };
    case 'attitude':
      return {
        color: 'text-pink-600',
        bgColor: 'bg-pink-100',
        borderColor: 'border-pink-300',
        label: '态度',
        icon: '💡',
      };
    default:
      return {
        color: 'text-slate-600',
        bgColor: 'bg-slate-100',
        borderColor: 'border-slate-300',
        label: '其他',
        icon: '📋',
      };
  }
}

/**
 * 获取优先级配置
 * @param priority 优先级
 * @returns 优先级配置对象
 */
export function getPriorityConfig(priority: PriorityLevel): {
  color: string;
  bgColor: string;
  borderColor: string;
  label: string;
} {
  switch (priority) {
    case 'high':
      return {
        color: 'text-red-600',
        bgColor: 'bg-red-100',
        borderColor: 'border-red-300',
        label: '高',
      };
    case 'medium':
      return {
        color: 'text-amber-600',
        bgColor: 'bg-amber-100',
        borderColor: 'border-amber-300',
        label: '中',
      };
    case 'low':
      return {
        color: 'text-slate-600',
        bgColor: 'bg-slate-100',
        borderColor: 'border-slate-300',
        label: '低',
      };
    default:
      return {
        color: 'text-slate-600',
        bgColor: 'bg-slate-100',
        borderColor: 'border-slate-300',
        label: '中',
      };
  }
}

export default {
  fetchObjectives,
  fetchObjectiveAssessment,
  createObjective,
  deleteObjective,
  triggerAssessment,
  getMatchLevelConfig,
  getObjectiveTypeConfig,
  getPriorityConfig,
};
