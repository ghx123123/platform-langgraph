import React, { memo, useState, useCallback } from 'react';
import type { Agent } from '../types';
import { useAgentStore } from '../stores/agentStore';
import { ConfirmDialog } from './ConfirmDialog';

interface AgentListProps {
  agents: Agent[];
  selectedAgent: Agent | null;
  onSelectAgent: (agent: Agent | null) => void;
}

function AgentListComponent({ agents, selectedAgent, onSelectAgent }: AgentListProps) {
  const { deleteAgent, cloneAgent } = useAgentStore();
  const [deleteTarget, setDeleteTarget] = useState<Agent | null>(null);

  const getStatusColor = (status: Agent['status']) => {
    switch (status) {
      case 'online': return 'bg-emerald-500';
      case 'busy': return 'bg-amber-500';
      case 'offline': return 'bg-slate-400';
    }
  };

  const handleClone = async (e: React.MouseEvent, agent: Agent) => {
    e.stopPropagation();
    try {
      await cloneAgent(agent.id);
    } catch (err) {
      console.error('Failed to clone agent:', err);
    }
  };

  const handleDeleteClick = useCallback((e: React.MouseEvent, agent: Agent) => {
    e.stopPropagation();
    setDeleteTarget(agent);
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      await deleteAgent(deleteTarget.id);
      if (selectedAgent?.id === deleteTarget.id) {
        onSelectAgent(null);
      }
    } catch (err) {
      console.error('Failed to delete agent:', err);
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, deleteAgent, selectedAgent, onSelectAgent]);

  const handleCancelDelete = useCallback(() => {
    setDeleteTarget(null);
  }, []);

  return (
    <>
      <div className="flex-1 overflow-auto p-3">
        <h2 className="text-sm font-semibold text-slate-500 uppercase px-2 py-3 tracking-wider">Agents</h2>
        <div className="space-y-2">
          {agents.map(agent => (
            <div
              key={agent.id}
              onClick={() => onSelectAgent(agent)}
              className={`
                group p-3 rounded-xl cursor-pointer transition-all duration-200 border
                ${selectedAgent?.id === agent.id
                  ? 'bg-white border-blue-300 shadow-md shadow-blue-100'
                  : 'bg-white border-slate-200 hover:border-blue-200 hover:shadow-sm'
                }
              `}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{agent.avatar}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`font-semibold truncate ${selectedAgent?.id === agent.id ? 'text-blue-700' : 'text-slate-700'}`}>
                      {agent.name}
                    </span>
                    <span className={`w-2.5 h-2.5 rounded-full ${getStatusColor(agent.status)} ring-2 ring-white`} />
                  </div>
                  <p className={`text-xs truncate mt-0.5 ${selectedAgent?.id === agent.id ? 'text-blue-500' : 'text-slate-400'}`}>
                    {agent.description || 'No description'}
                  </p>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={(e) => handleClone(e, agent)}
                  className="px-2 py-1 text-xs bg-slate-100 hover:bg-blue-50 text-slate-600 hover:text-blue-600 rounded-lg transition-colors"
                  title="Clone"
                >
                  📋
                </button>
                <button
                  onClick={(e) => handleDeleteClick(e, agent)}
                  className="px-2 py-1 text-xs bg-slate-100 hover:bg-red-50 text-slate-600 hover:text-red-600 rounded-lg transition-colors"
                  title="Delete"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}

          {agents.length === 0 && (
            <div className="text-center py-8">
              <p className="text-slate-400 text-sm">No agents yet</p>
              <p className="text-slate-300 text-xs mt-1">Create your first agent to start</p>
            </div>
          )}
        </div>
      </div>

      {/* Confirm Delete Dialog */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="删除 Agent"
        message={deleteTarget ? `确定要删除 Agent "${deleteTarget.name}" 吗？此操作不可恢复。` : ''}
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
        confirmText="删除"
        cancelText="取消"
        type="danger"
      />
    </>
  );
}

// Memoized export to prevent unnecessary re-renders
export const AgentList = memo(AgentListComponent);
export default AgentList;
