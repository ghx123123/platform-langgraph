import { create } from 'zustand';
import type {
  AgentNodeData,
  AgentEdgeData,
  TaskExecution,
  ExecutionTimelineEvent,
  RealtimeMessage,
  ExecutionSession,
  ExecutionStatistics,
  AgentStatus,
  TaskStatus,
} from '../types/visualization';

interface ExecutionState {
  // Agent collaboration graph data
  agentNodes: AgentNodeData[];
  agentEdges: AgentEdgeData[];

  // Task execution state
  tasks: TaskExecution[];
  taskQueue: string[]; // task IDs in order

  // Realtime message stream
  messageStream: RealtimeMessage[];
  maxMessages: number;

  // Current execution session
  activeSession: ExecutionSession | null;

  // Statistics
  statistics: ExecutionStatistics | null;

  // Timeline events
  timelineEvents: ExecutionTimelineEvent[];

  // Active agent (currently speaking/thinking)
  activeAgentId: string | null;

  // Loading state
  loading: boolean;
  error: string | null;

  // Actions
  setAgentNodes: (nodes: AgentNodeData[]) => void;
  updateAgentStatus: (agentId: string, status: AgentStatus, currentTask?: string) => void;
  updateAgentMessageCount: (agentId: string, increment?: number) => void;
  setAgentEdges: (edges: AgentEdgeData[]) => void;
  addAgentEdge: (edge: AgentEdgeData) => void;

  addTask: (task: TaskExecution) => void;
  updateTaskStatus: (taskId: string, status: TaskStatus, result?: string) => void;
  updateTaskProgress: (taskId: string, progress: number) => void;

  addMessage: (message: RealtimeMessage) => void;
  clearMessages: () => void;

  setActiveSession: (session: ExecutionSession | null) => void;
  setStatistics: (stats: ExecutionStatistics) => void;

  addTimelineEvent: (event: ExecutionTimelineEvent) => void;

  setActiveAgent: (agentId: string | null) => void;

  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  reset: () => void;
}

const initialState = {
  agentNodes: [],
  agentEdges: [],
  tasks: [],
  taskQueue: [],
  messageStream: [],
  maxMessages: 100,
  activeSession: null,
  statistics: null,
  timelineEvents: [],
  activeAgentId: null,
  loading: false,
  error: null,
};

export const useExecutionStore = create<ExecutionState>((set) => ({
  ...initialState,

  setAgentNodes: (nodes: AgentNodeData[]) => {
    set({ agentNodes: nodes });
  },

  updateAgentStatus: (agentId: string, status: AgentStatus, currentTask?: string) => {
    set((state) => ({
      agentNodes: state.agentNodes.map((node) =>
        node.id === agentId
          ? { ...node, status, currentTask: currentTask ?? node.currentTask }
          : node
      ),
    }));
  },

  updateAgentMessageCount: (agentId: string, increment = 1) => {
    set((state) => ({
      agentNodes: state.agentNodes.map((node) =>
        node.id === agentId
          ? { ...node, messageCount: node.messageCount + increment }
          : node
      ),
    }));
  },

  setAgentEdges: (edges: AgentEdgeData[]) => {
    set({ agentEdges: edges });
  },

  addAgentEdge: (edge: AgentEdgeData) => {
    set((state) => {
      // Check if edge already exists
      const existingIndex = state.agentEdges.findIndex(
        (e) => e.source === edge.source && e.target === edge.target
      );

      if (existingIndex >= 0) {
        // Update existing edge
        const updatedEdges = [...state.agentEdges];
        updatedEdges[existingIndex] = {
          ...updatedEdges[existingIndex],
          count: updatedEdges[existingIndex].count + 1,
          lastMessage: edge.lastMessage,
          animated: true,
        };
        return { agentEdges: updatedEdges };
      }

      // Add new edge
      return { agentEdges: [...state.agentEdges, { ...edge, animated: true }] };
    });

    // Clear animation flag after animation completes
    setTimeout(() => {
      set((state) => ({
        agentEdges: state.agentEdges.map((e) =>
          e.id === edge.id ? { ...e, animated: false } : e
        ),
      }));
    }, 1000);
  },

  addTask: (task: TaskExecution) => {
    set((state) => ({
      tasks: [...state.tasks, task],
      taskQueue: [...state.taskQueue, task.id],
    }));
  },

  updateTaskStatus: (taskId: string, status: TaskStatus, result?: string) => {
    set((state) => ({
      tasks: state.tasks.map((task) =>
        task.id === taskId
          ? {
              ...task,
              status,
              result: result ?? task.result,
              completedAt: status === 'completed' || status === 'failed' ? new Date().toISOString() : task.completedAt,
            }
          : task
      ),
      taskQueue:
        status === 'completed' || status === 'failed'
          ? state.taskQueue.filter((id) => id !== taskId)
          : state.taskQueue,
    }));
  },

  updateTaskProgress: (taskId: string, progress: number) => {
    set((state) => ({
      tasks: state.tasks.map((task) =>
        task.id === taskId ? { ...task, progress } : task
      ),
    }));
  },

  addMessage: (message: RealtimeMessage) => {
    set((state) => {
      const messages = [...state.messageStream, message];
      // Keep only the last maxMessages
      if (messages.length > state.maxMessages) {
        messages.shift();
      }
      return { messageStream: messages };
    });
  },

  clearMessages: () => {
    set({ messageStream: [] });
  },

  setActiveSession: (session: ExecutionSession | null) => {
    set({ activeSession: session });
  },

  setStatistics: (stats: ExecutionStatistics) => {
    set({ statistics: stats });
  },

  addTimelineEvent: (event: ExecutionTimelineEvent) => {
    set((state) => ({
      timelineEvents: [...state.timelineEvents, event],
    }));
  },

  setActiveAgent: (agentId: string | null) => {
    set({ activeAgentId: agentId });
  },

  setLoading: (loading: boolean) => {
    set({ loading });
  },

  setError: (error: string | null) => {
    set({ error });
  },

  reset: () => {
    set(initialState);
  },
}));

// Selector helpers
export const selectRunningTasks = (state: ExecutionState) =>
  state.tasks.filter((t) => t.status === 'running');

export const selectQueuedTasks = (state: ExecutionState) =>
  state.tasks.filter((t) => t.status === 'queued');

export const selectCompletedTasks = (state: ExecutionState) =>
  state.tasks.filter((t) => t.status === 'completed');

export const selectActiveAgents = (state: ExecutionState) =>
  state.agentNodes.filter((n) => n.status !== 'idle' && n.status !== 'completed');