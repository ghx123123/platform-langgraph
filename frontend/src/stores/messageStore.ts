import { create } from 'zustand';
import type { Message } from '../types';

const API_BASE = '/api';

interface MessageState {
  messages: Message[];
  loading: boolean;
  error: string | null;
  searchQuery: string;
  filteredMessages: Message[];

  // Actions
  fetchMessages: (limit?: number) => Promise<void>;
  sendMessage: (to: string, content: Record<string, any>, msgType?: string) => Promise<void>;
  broadcastMessage: (content: Record<string, any>) => Promise<void>;
  addMessage: (message: Message) => void;
  searchMessages: (query: string) => void;
  exportMessages: (format: 'markdown' | 'json') => string;
  clearSearch: () => void;
}

export const useMessageStore = create<MessageState>((set, get) => ({
  messages: [],
  loading: false,
  error: null,
  searchQuery: '',
  filteredMessages: [],

  fetchMessages: async (limit = 50) => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API_BASE}/messages/history?limit=${limit}`);
      if (!res.ok) throw new Error('Failed to fetch messages');
      const messages = await res.json();
      set({ messages, filteredMessages: messages, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  sendMessage: async (to: string, content: Record<string, any>, msgType = 'chat') => {
    set({ error: null });
    try {
      const res = await fetch(`${API_BASE}/messages/send?from_agent=current_user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to, content, msg_type: msgType }),
      });
      if (!res.ok) throw new Error('Failed to send message');
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  broadcastMessage: async (content: Record<string, any>) => {
    set({ error: null });
    try {
      const res = await fetch(`${API_BASE}/messages/broadcast?from_agent=current_user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error('Failed to broadcast');
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  addMessage: (message: Message) => {
    set(state => {
      const newMessages = [...state.messages, message];
      return {
        messages: newMessages,
        filteredMessages: state.searchQuery
          ? newMessages.filter(m =>
              JSON.stringify(m.content).toLowerCase().includes(state.searchQuery.toLowerCase())
            )
          : newMessages,
      };
    });
  },

  searchMessages: (query: string) => {
    const { messages } = get();
    const filtered = query
      ? messages.filter(m =>
          JSON.stringify(m.content).toLowerCase().includes(query.toLowerCase()) ||
          m.from_agent.toLowerCase().includes(query.toLowerCase())
        )
      : messages;
    set({ searchQuery: query, filteredMessages: filtered });
  },

  exportMessages: (format: 'markdown' | 'json') => {
    const { messages } = get();
    if (format === 'json') {
      return JSON.stringify(messages, null, 2);
    }
    // Markdown format
    return messages.map(m => {
      const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
      return `**${m.from_agent}** (${new Date(m.created_at).toLocaleString()}):\n${content}\n---\n`;
    }).join('\n');
  },

  clearSearch: () => {
    const { messages } = get();
    set({ searchQuery: '', filteredMessages: messages });
  },
}));
