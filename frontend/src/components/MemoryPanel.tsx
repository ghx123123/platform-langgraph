import { useState, useEffect } from 'react';
import type { Agent, Memory } from '../types';

interface MemoryPanelProps {
  agent: Agent;
}

const API_BASE = '/api';

export function MemoryPanel({ agent }: MemoryPanelProps) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'stm' | 'ltm' | 'episodic'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchMemories();
  }, [agent.id]);

  const fetchMemories = async () => {
    try {
      const res = await fetch(`${API_BASE}/agents/${agent.id}/memories`);
      if (res.ok) {
        const data = await res.json();
        setMemories(data);
      }
    } catch (err) {
      console.error('Failed to fetch memories:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (memoryId: string) => {
    try {
      await fetch(`${API_BASE}/agents/${agent.id}/memories/${memoryId}`, {
        method: 'DELETE',
      });
      setMemories(prev => prev.filter(m => m.id !== memoryId));
    } catch (err) {
      console.error('Failed to delete memory:', err);
    }
  };

  const filteredMemories = memories.filter(memory => {
    if (filter !== 'all' && memory.memory_type !== filter) return false;
    if (searchQuery && !memory.content.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    return true;
  });

  const getMemoryTypeLabel = (type: Memory['memory_type']) => {
    switch (type) {
      case 'stm': return '🟡 Short-term';
      case 'ltm': return '🟢 Long-term';
      case 'episodic': return '🔵 Episodic';
    }
  };

  if (loading) {
    return <div className="text-center text-gray-400 py-8">Loading memories...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Memory</h3>
        <div className="flex gap-2">
          <select
            value={filter}
            onChange={e => setFilter(e.target.value as any)}
            className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm"
          >
            <option value="all">All</option>
            <option value="stm">Short-term</option>
            <option value="ltm">Long-term</option>
            <option value="episodic">Episodic</option>
          </select>
        </div>
      </div>

      {/* Search */}
      <input
        type="text"
        value={searchQuery}
        onChange={e => setSearchQuery(e.target.value)}
        placeholder="Search memories..."
        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
      />

      {/* Memory List */}
      <div className="space-y-2">
        {filteredMemories.map(memory => (
          <div
            key={memory.id}
            className="bg-gray-700 rounded-lg p-3 group"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <span className="text-xs text-gray-400">
                  {getMemoryTypeLabel(memory.memory_type)}
                </span>
                <p className="text-sm mt-1 break-words">{memory.content}</p>
                {memory.metadata && Object.keys(memory.metadata).length > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    {JSON.stringify(memory.metadata)}
                  </p>
                )}
              </div>
              <button
                onClick={() => handleDelete(memory.id)}
                className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-400 transition-opacity"
              >
                🗑️
              </button>
            </div>
          </div>
        ))}

        {filteredMemories.length === 0 && (
          <p className="text-center text-gray-500 py-4">
            {searchQuery ? 'No matching memories' : 'No memories yet'}
          </p>
        )}
      </div>

      {/* Stats */}
      <div className="text-xs text-gray-500 pt-2 border-t border-gray-700">
        Total: {memories.length} memories
        ({memories.filter(m => m.memory_type === 'stm').length} STM,
        {memories.filter(m => m.memory_type === 'ltm').length} LTM,
        {memories.filter(m => m.memory_type === 'episodic').length} Episodic)
      </div>
    </div>
  );
}
