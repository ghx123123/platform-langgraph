// interactionApi.ts - 互动路径数据 API 服务

export type InteractionType = 'QUESTION' | 'ANSWER' | 'COMMENT';
export type AgentTypeInPath = 'teacher' | 'student' | 'supervisor';

export interface InteractionNode {
  id: string;
  agent_id: string;
  agent_name: string;
  agent_type: AgentTypeInPath;
  agent_avatar?: string;
  content: string;
  interaction_type: InteractionType;
  parent_id?: string | null;
  created_at: string;
  iteration: number;
  phase?: string;
}

export interface InteractionStatistics {
  total_interactions: number;
  question_count: number;
  answer_count: number;
  comment_count: number;
  qa_coverage: number; // 回答覆盖率 (0-100)
  frequent_questions: Array<{
    content: string;
    count: number;
    similarity_group: string[];
  }>;
}

export interface InteractionPathData {
  nodes: InteractionNode[];
  statistics: InteractionStatistics;
}

/**
 * 获取教学会话的互动路径数据
 * @param sessionId 教学会话ID
 * @returns 互动路径数据
 */
export async function fetchInteractionPath(sessionId: string): Promise<InteractionPathData> {
  try {
    // 尝试从专用API获取数据
    const response = await fetch(`/api/teaching/sessions/${sessionId}/interaction-path`);
    
    if (response.ok) {
      const data = await response.json();
      return {
        nodes: data.nodes || [],
        statistics: data.statistics || calculateStatistics(data.nodes || []),
      };
    }
    
    // 如果专用API不存在，从现有消息数据构建
    const [sessionRes, messagesRes] = await Promise.all([
      fetch(`/api/teaching/sessions/${sessionId}`),
      fetch(`/api/teaching/sessions/${sessionId}/messages`),
    ]);

    if (!sessionRes.ok) {
      throw new Error(`获取会话数据失败: ${sessionRes.status}`);
    }

    if (!messagesRes.ok) {
      throw new Error(`获取消息数据失败: ${messagesRes.status}`);
    }

    // 读取会话数据（用于未来扩展）
    await sessionRes.json();
    const messagesData = await messagesRes.json();

    // 将TeachingMessage转换为InteractionNode
    const nodes: InteractionNode[] = (messagesData.messages || []).map((msg: any) => ({
      id: msg.id,
      agent_id: msg.agent_id,
      agent_name: msg.agent_name,
      agent_type: msg.agent_type,
      agent_avatar: getAgentAvatar(msg.agent_type, msg.agent_name),
      content: msg.content,
      interaction_type: mapPhaseToInteractionType(msg.phase),
      parent_id: findParentId(msg, messagesData.messages || []),
      created_at: msg.created_at,
      iteration: msg.iteration || 1,
      phase: msg.phase,
    }));

    const statistics = calculateStatistics(nodes);

    return {
      nodes,
      statistics,
    };
  } catch (error) {
    console.error('[InteractionApi] 获取互动路径失败:', error);
    throw error instanceof Error ? error : new Error('获取互动路径数据失败');
  }
}

/**
 * 根据阶段映射到互动类型
 */
function mapPhaseToInteractionType(phase?: string): InteractionType {
  switch (phase) {
    case 'student_question':
      return 'QUESTION';
    case 'teacher_answer':
    case 'teach_knowledge':
    case 'design':
      return 'ANSWER';
    case 'supervisor_comment':
      return 'COMMENT';
    default:
      return 'COMMENT';
  }
}

/**
 * 获取Agent头像
 */
function getAgentAvatar(agentType: string, agentName?: string): string {
  if (agentType === 'teacher') return '👨‍🏫';
  if (agentType === 'supervisor') return '🔍';
  // 学生类型
  if (agentName?.includes('优秀')) return '🎓';
  if (agentName?.includes('中等')) return '📚';
  return '📖';
}

/**
 * 查找父节点ID（问答关联）
 */
function findParentId(message: any, allMessages: any[]): string | undefined {
  // 如果是学生提问，查找对应的教师回答
  if (message.phase === 'teacher_answer') {
    // 找到同轮次的学生提问作为父节点
    const parentQuestion = allMessages.find(
      m => m.phase === 'student_question' && 
           m.iteration === message.iteration &&
           m.created_at < message.created_at
    );
    return parentQuestion?.id;
  }
  
  // 如果是教师回答，查找对应的学生提问
  if (message.phase === 'student_question') {
    const teacherAnswer = allMessages.find(
      m => m.phase === 'teach_knowledge' && 
           m.iteration === message.iteration &&
           m.created_at < message.created_at
    );
    return teacherAnswer?.id;
  }
  
  // 督导点评关联到教师回答
  if (message.phase === 'supervisor_comment') {
    const teacherAnswer = allMessages.find(
      m => (m.phase === 'teacher_answer' || m.phase === 'teach_knowledge') && 
           m.iteration === message.iteration &&
           m.created_at < message.created_at
    );
    return teacherAnswer?.id;
  }
  
  return undefined;
}

/**
 * 计算统计数据
 */
function calculateStatistics(nodes: InteractionNode[]): InteractionStatistics {
  const questionCount = nodes.filter(n => n.interaction_type === 'QUESTION').length;
  const answerCount = nodes.filter(n => n.interaction_type === 'ANSWER').length;
  const commentCount = nodes.filter(n => n.interaction_type === 'COMMENT').length;
  
  // 计算回答覆盖率
  const answeredQuestions = nodes.filter(n => {
    if (n.interaction_type !== 'QUESTION') return false;
    // 查找是否有对应的回答
    return nodes.some(child => 
      child.parent_id === n.id && child.interaction_type === 'ANSWER'
    );
  }).length;
  
  const qaCoverage = questionCount > 0 
    ? Math.round((answeredQuestions / questionCount) * 100) 
    : 0;

  // 统计高频问题（基于内容相似度）
  const questions = nodes.filter(n => n.interaction_type === 'QUESTION');
  const frequentQuestions = findFrequentQuestions(questions);

  return {
    total_interactions: nodes.length,
    question_count: questionCount,
    answer_count: answerCount,
    comment_count: commentCount,
    qa_coverage: qaCoverage,
    frequent_questions: frequentQuestions,
  };
}

/**
 * 查找高频问题（基于关键词相似度）
 */
function findFrequentQuestions(questions: InteractionNode[]): InteractionStatistics['frequent_questions'] {
  if (questions.length === 0) return [];

  const groups: Map<string, string[]> = new Map();
  
  // 简单的关键词提取和分组
  questions.forEach(q => {
    const keywords = extractKeywords(q.content);
    const key = keywords.slice(0, 3).join(' '); // 取前3个关键词作为组标识
    
    if (groups.has(key)) {
      groups.get(key)!.push(q.id);
    } else {
      groups.set(key, [q.id]);
    }
  });

  // 转换为数组并过滤出频次高的
  return Array.from(groups.entries())
    .filter(([_, ids]) => ids.length >= 2)
    .map(([key, ids]) => {
      const representative = questions.find(q => q.id === ids[0]);
      return {
        content: representative?.content.slice(0, 50) + '...' || key,
        count: ids.length,
        similarity_group: ids,
      };
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

/**
 * 提取关键词（简单实现）
 */
function extractKeywords(content: string): string[] {
  // 移除标点符号和停用词
  const stopWords = ['的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '什么', '为什么', '怎么', '吗', '呢', '吗'];
  
  return content
    .replace(/[，。？！；：""''（）【】《》、,.?!;:\"'()[\]<>]/g, ' ')
    .split(/\s+/)
    .filter(word => word.length > 1 && !stopWords.includes(word))
    .slice(0, 5);
}

/**
 * 构建树形结构
 */
export function buildTreeStructure(nodes: InteractionNode[]): InteractionNode[] {
  const nodeMap = new Map<string, InteractionNode & { children?: InteractionNode[] }>();
  
  // 创建节点映射
  nodes.forEach(node => {
    nodeMap.set(node.id, { ...node, children: [] });
  });
  
  // 构建父子关系
  const rootNodes: InteractionNode[] = [];
  
  nodeMap.forEach(node => {
    if (node.parent_id && nodeMap.has(node.parent_id)) {
      const parent = nodeMap.get(node.parent_id)!;
      if (!parent.children) parent.children = [];
      parent.children.push(node);
    } else {
      rootNodes.push(node);
    }
  });
  
  // 按时间排序
  rootNodes.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  
  return rootNodes;
}

/**
 * 按时间线分组
 */
export function groupByTimeline(nodes: InteractionNode[]): Array<{
  iteration: number;
  nodes: InteractionNode[];
}> {
  const groups = new Map<number, InteractionNode[]>();
  
  nodes.forEach(node => {
    const iter = node.iteration || 1;
    if (!groups.has(iter)) {
      groups.set(iter, []);
    }
    groups.get(iter)!.push(node);
  });
  
  return Array.from(groups.entries())
    .map(([iteration, nodes]) => ({
      iteration,
      nodes: nodes.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    }))
    .sort((a, b) => a.iteration - b.iteration);
}

/**
 * 获取节点类型样式
 */
export function getNodeTypeConfig(type: InteractionType): {
  color: string;
  bgColor: string;
  borderColor: string;
  label: string;
  icon: string;
} {
  switch (type) {
    case 'QUESTION':
      return {
        color: 'text-blue-600',
        bgColor: 'bg-blue-50',
        borderColor: 'border-blue-300',
        label: '学生提问',
        icon: '❓',
      };
    case 'ANSWER':
      return {
        color: 'text-emerald-600',
        bgColor: 'bg-emerald-50',
        borderColor: 'border-emerald-300',
        label: '教师回答',
        icon: '💬',
      };
    case 'COMMENT':
      return {
        color: 'text-orange-600',
        bgColor: 'bg-orange-50',
        borderColor: 'border-orange-300',
        label: '督导点评',
        icon: '⭐',
      };
    default:
      return {
        color: 'text-slate-600',
        bgColor: 'bg-slate-50',
        borderColor: 'border-slate-300',
        label: '其他',
        icon: '📝',
      };
  }
}

export default {
  fetchInteractionPath,
  buildTreeStructure,
  groupByTimeline,
  getNodeTypeConfig,
};
