import { create } from 'zustand';
import type { Agent, CreateAgentRequest } from '../types';

const API_BASE = '/api';

interface AgentState {
  agents: Agent[];
  selectedAgent: Agent | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchAgents: () => Promise<void>;
  createAgent: (req: CreateAgentRequest) => Promise<Agent>;
  updateAgent: (id: string, updates: Partial<Agent>) => Promise<void>;
  deleteAgent: (id: string) => Promise<void>;
  cloneAgent: (id: string) => Promise<Agent>;
  selectAgent: (agent: Agent | null) => void;
  setError: (error: string | null) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  selectedAgent: null,
  loading: false,
  error: null,

  fetchAgents: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/agents`);
      if (!res.ok) throw new Error('Failed to fetch agents');
      const agents = await res.json();
      set({ agents, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  createAgent: async (req: CreateAgentRequest) => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/agents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (!res.ok) throw new Error('Failed to create agent');
      const agent = await res.json();
      set(state => ({ agents: [...state.agents, agent], loading: false }));
      return agent;
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  updateAgent: async (id: string, updates: Partial<Agent>) => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/agents/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      if (!res.ok) throw new Error('Failed to update agent');
      const updated = await res.json();
      set(state => ({
        agents: state.agents.map(a => a.id === id ? updated : a),
        selectedAgent: state.selectedAgent?.id === id ? updated : state.selectedAgent,
        loading: false,
      }));
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  deleteAgent: async (id: string) => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/agents/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete agent');
      set(state => ({
        agents: state.agents.filter(a => a.id !== id),
        selectedAgent: state.selectedAgent?.id === id ? null : state.selectedAgent,
        loading: false,
      }));
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  cloneAgent: async (id: string) => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/agents/${id}/clone`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to clone agent');
      const agent = await res.json();
      set(state => ({ agents: [...state.agents, agent], loading: false }));
      return agent;
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      throw e;
    }
  },

  selectAgent: (agent: Agent | null) => {
    set({ selectedAgent: agent });
  },

  setError: (error: string | null) => {
    set({ error });
  },
}));
