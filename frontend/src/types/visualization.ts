// ============================================================
// Agent Collaboration Graph Types
// ============================================================

export type AgentType = 'proponent' | 'opponent' | 'teacher' | 'student' | 'supervisor' | 'moderator' | 'reporter';

export type AgentStatus = 'idle' | 'thinking' | 'speaking' | 'waiting' | 'completed' | 'error';

export interface AgentNodeData {
  id: string;
  label: string;
  type: AgentType;
  status: AgentStatus;
  avatar: string;
  currentTask?: string;
  messageCount: number;
  [key: string]: unknown; // Index signature for React Flow compatibility
}

export interface AgentEdgeData {
  id: string;
  source: string;
  target: string;
  type: 'message' | 'subtask' | 'broadcast';
  count: number;
  lastMessage?: string;
  animated?: boolean;
  [key: string]: unknown; // Index signature for React Flow compatibility
}

// ============================================================
// Task Execution Types
// ============================================================

export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export type TaskPriority = 'low' | 'medium' | 'high' | 'critical';

export interface TaskExecution {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: TaskPriority;
  assignedAgent?: string;
  progress: number;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  result?: string;
  error?: string;
  [key: string]: unknown;
}

export interface ExecutionTimelineEvent {
  id: string;
  timestamp: string;
  type: 'task_start' | 'task_complete' | 'task_fail' | 'agent_join' | 'agent_leave' | 'message_sent' | 'round_start' | 'round_end';
  agentId?: string;
  taskId?: string;
  details: Record<string, unknown>;
}

// ============================================================
// Data Import Types
// ============================================================

export type ParseStage = 'idle' | 'uploading' | 'extracting' | 'analyzing' | 'building' | 'completed' | 'failed';

export interface KnowledgePoint {
  id: string;
  title: string;
  description: string;
  relevance: number;
  sourceParagraph?: string;
}

export interface ImportProgress {
  stage: ParseStage;
  progress: number;
  message?: string;
}

export interface ImportResult {
  docId: string;
  fileName: string;
  courseName: string;
  chapterTitle: string;
  totalParagraphs: number;
  knowledgePoints: KnowledgePoint[];
  summary: string;
  createdAt: string;
}

// ============================================================
// Realtime Message Types
// ============================================================

export interface RealtimeMessage {
  id: string;
  fromAgent: string;
  fromAgentLabel: string;
  toAgent: string;
  toAgentLabel: string;
  content: string;
  timestamp: string;
  type: 'chat' | 'debate' | 'teach' | 'system';
  animated?: boolean;
}

// ============================================================
// Execution Session Types
// ============================================================

export type SessionType = 'debate' | 'teaching' | 'chat';

export type SessionStatus = 'pending' | 'active' | 'paused' | 'completed' | 'failed';

export interface ExecutionSession {
  id: string;
  type: SessionType;
  status: SessionStatus;
  title: string;
  startTime: string;
  endTime?: string;
  currentRound?: number;
  maxRounds?: number;
  agentCount: number;
  taskCount: number;
  completedTaskCount: number;
}

// ============================================================
// Statistics Types
// ============================================================

export interface ExecutionStatistics {
  totalDuration: number;
  totalTokens: number;
  totalMessages: number;
  averageResponseTime: number;
  taskCompletionRate: number;
  agentActivity: Record<string, number>;
}

// ============================================================
// Debate Specific Types
// ============================================================

export interface DebateReport {
  summary: string;
  proponentPoints: string[];
  opponentPoints: string[];
  keyDisagreements: string[];
  conclusion: string;
  suggestions: string[];
  winner?: 'proponent' | 'opponent' | 'tie';
}

// ============================================================
// Teaching Specific Types
// ============================================================

export interface KnowledgeCoverage {
  knowledgePointId: string;
  title: string;
  covered: boolean;
  timesAccessed: number;
  masteryLevel: number;
}

export interface TeachingReport {
  interactionCount: number;
  knowledgeCoverage: KnowledgeCoverage[];
  quizResults: {
    totalQuestions: number;
    correctAnswers: number;
    score: number;
  };
  strengths: string[];
  weaknesses: string[];
  suggestions: string[];
}