// Agent types
export type AgentStatus = 'online' | 'busy' | 'offline';
export type MemoryScope = 'private' | 'team' | 'shared';
export type MessageType = 'chat' | 'subtask_request' | 'realtime_review' | 'clarification_request' | 'response' | 'escalation' | 'broadcast';
export type Priority = 'P0' | 'P1' | 'P2';

export interface Agent {
  id: string;
  name: string;
  role: string;
  description: string;
  avatar: string;
  tools: string[];
  memory_scope: MemoryScope;
  status: AgentStatus;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  msg_type: MessageType;
  priority: Priority;
  from_agent: string;
  to: string;
  content: Record<string, any>;
  deadline: string;
  callback?: string;
  created_at: string;
}

export interface Memory {
  id: string;
  agent_id: string;
  memory_type: 'stm' | 'ltm' | 'episodic';
  key?: string;
  content: string;
  embedding?: number[];
  metadata: Record<string, any>;
  created_at: string;
  expires_at?: string;
}

// Request types
export interface CreateAgentRequest {
  name: string;
  role: string;
  description?: string;
  avatar?: string;
  tools?: string[];
  memory_scope?: MemoryScope;
}

export interface ThinkRequest {
  prompt: string;
}

export interface SendMessageRequest {
  msg_type: MessageType;
  priority?: Priority;
  to: string;
  content: Record<string, any>;
  deadline?: string;
}

// WebSocket types
export interface WSMessage {
  type: 'message' | 'ping' | 'pong';
  msg_type?: MessageType;
  from?: string;
  to?: string;
  content?: Record<string, any>;
  priority?: Priority;
}

// Debate types
export type SessionStatus = 'pending' | 'ready' | 'active' | 'paused' | 'completed' | 'failed';
export type AgentRole = 'proponent' | 'opponent' | 'moderator' | 'reporter';
export type DebateRole = 'debate' | 'challenge' | 'rebuttal' | 'summary' | 'comment';

export interface KnowledgePoint {
  title: string;
  chapter: string;
  is_key_point: boolean;
  difficulty_level: string;
  keywords: string[];
}

export interface DebateSession {
  id: string;
  title: string;
  document_id?: string;
  status: SessionStatus;
  current_round: number;
  max_rounds: number;
  knowledge_points: KnowledgePoint[];
  raw_text: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface DebateAgent {
  id: string;
  session_id: string;
  name: string;
  role: AgentRole;
  stance: string;
  system_prompt: string;
  avatar: string;
  status: 'idle' | 'ready' | 'debating' | 'waiting';
  created_at: string;
}

export interface DebateMessage {
  id: string;
  session_id: string;
  agent_id: string;
  agent_name: string;
  agent_role: AgentRole;
  round: number;
  msg_type: DebateRole;
  content: string;
  target_agent_id?: string;
  is_final: boolean;
  created_at: string;
}

export interface DebateReport {
  session_id: string;
  summary: string;
  proponent_points: string[];
  opponent_points: string[];
  key_disagreements: string[];
  conclusion: string;
  suggestions: string[];
  generated_at: string;
}

// Teaching types
export type TeachingStatus = 'pending' | 'designing' | 'teaching' | 'paused' | 'completed' | 'failed';
export type TeachingPhase = 'design' | 'teach_knowledge' | 'student_question' | 'teacher_answer' | 'supervisor_comment' | 'iteration_complete';
export type AgentType = 'teacher' | 'student' | 'supervisor';
export type StudentLevel = 'high' | 'medium' | 'low';

export interface TeachingSession {
  id: string;
  title: string;
  document_id?: string;
  status: TeachingStatus;
  current_iteration: number;
  max_iterations: number;
  current_phase: TeachingPhase;
  knowledge_points: KnowledgePoint[];
  raw_text: string;
  teaching_script: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface TeachingAgent {
  id: string;
  session_id: string;
  name: string;
  agent_type: AgentType;
  level?: StudentLevel;
  system_prompt: string;
  avatar: string;
  status: 'idle' | 'teaching' | 'answering' | 'commenting';
}

export interface TeachingMessageReference {
  agent_id: string;
  agent_name: string;
  suggestion: string;
  dimension: string;
}

export interface TeachingMessage {
  id: string;
  session_id: string;
  agent_id: string;
  agent_name: string;
  agent_type: AgentType;
  phase: TeachingPhase;
  iteration: number;
  content: string;
  references?: TeachingMessageReference[];
  created_at: string;
}
