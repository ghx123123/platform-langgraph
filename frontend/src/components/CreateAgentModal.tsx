import React, { useState } from 'react';
import { useAgentStore } from '../stores/agentStore';
import type { CreateAgentRequest } from '../types';

interface CreateAgentModalProps {
  onClose: () => void;
  onCreated: () => void;
}

const ROLES = [
  { id: 'coder', name: '💻 编码者', description: '执行具体编码任务' },
  { id: 'reviewer', name: '🔎 审查者', description: '代码审查、规范检查' },
  { id: 'designer', name: '📐 设计者', description: '模块设计、技术方案' },
  { id: 'verifier', name: '✅ 验证者', description: '审查问题、验证方案' },
  { id: 'diagnostician', name: '🩺 诊断者', description: '系统问题、根因分析' },
  { id: 'clarifier', name: '🔍 澄清者', description: '需求澄清、技术难点' },
  { id: 'challenger', name: '⚔️ 质询者', description: '逻辑挑战、漏洞发现' },
];

const AVATARS = ['🤖', '🦊', '🐸', '🦁', '🐼', '🐨', '🐯', '🦉', '🦅', '🐬'];

export function CreateAgentModal({ onClose, onCreated }: CreateAgentModalProps) {
  const { createAgent, loading } = useAgentStore();
  const [form, setForm] = useState<CreateAgentRequest>({
    name: '',
    role: '',
    description: '',
    avatar: '🤖',
    tools: [],
    memory_scope: 'private',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createAgent(form);
      onCreated();
    } catch (err) {
      console.error('Failed to create agent:', err);
    }
  };

  const handleRoleSelect = (roleId: string) => {
    const role = ROLES.find(r => r.id === roleId);
    setForm(prev => ({
      ...prev,
      role: `You are a ${roleId}. ${role?.description}`,
      description: role?.description || '',
    }));
  };

  return (
    <div className="fixed inset-0 bg-slate-900/30 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-xl border border-slate-200/60 p-6 w-full max-w-lg max-h-[90vh] overflow-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center text-xl text-white shadow-md">
              🤖
            </div>
            <h2 className="text-xl font-bold text-slate-800">创建 Agent</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium mb-2 text-slate-700">名称</label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
              placeholder="输入 Agent 名称"
              required
            />
          </div>

          {/* Avatar */}
          <div>
            <label className="block text-sm font-medium mb-2 text-slate-700">头像</label>
            <div className="flex gap-2 flex-wrap">
              {AVATARS.map(avatar => (
                <button
                  key={avatar}
                  type="button"
                  onClick={() => setForm(prev => ({ ...prev, avatar }))}
                  className={`w-11 h-11 text-xl rounded-xl flex items-center justify-center transition-all shadow-sm ${
                    form.avatar === avatar
                      ? 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg scale-110'
                      : 'bg-slate-100 hover:bg-slate-200 hover:scale-105'
                  }`}
                >
                  {avatar}
                </button>
              ))}
            </div>
          </div>

          {/* Role Presets */}
          <div>
            <label className="block text-sm font-medium mb-2 text-slate-700">角色预设</label>
            <div className="grid grid-cols-2 gap-2">
              {ROLES.map(role => (
                <button
                  key={role.id}
                  type="button"
                  onClick={() => handleRoleSelect(role.id)}
                  className="p-3 text-left bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-300 rounded-xl transition-all group"
                >
                  <span className="font-medium text-slate-800 group-hover:text-blue-700">{role.name}</span>
                  <p className="text-xs text-slate-500 mt-0.5">{role.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Custom Role */}
          <div>
            <label className="block text-sm font-medium mb-2 text-slate-700">自定义角色描述</label>
            <textarea
              value={form.role}
              onChange={e => setForm(prev => ({ ...prev, role: e.target.value }))}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all resize-none"
              rows={3}
              placeholder="描述 Agent 的角色和行为..."
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium mb-2 text-slate-700">简短描述</label>
            <input
              type="text"
              value={form.description}
              onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all"
              placeholder="简短描述"
            />
          </div>

          {/* Memory Scope */}
          <div>
            <label className="block text-sm font-medium mb-2 text-slate-700">记忆范围</label>
            <select
              value={form.memory_scope}
              onChange={e => setForm(prev => ({ ...prev, memory_scope: e.target.value as any }))}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all cursor-pointer"
            >
              <option value="private">私有 - 仅当前 Agent 可访问</option>
              <option value="team">团队 - 团队成员共享</option>
              <option value="shared">共享 - 所有 Agent 可访问</option>
            </select>
          </div>

          {/* Submit */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium rounded-xl transition-colors border border-slate-200"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={loading || !form.name || !form.role}
              className="flex-1 px-4 py-2.5 bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 disabled:from-slate-300 disabled:to-slate-400 disabled:cursor-not-allowed text-white font-medium rounded-xl transition-all shadow-md hover:shadow-lg disabled:shadow-none"
            >
              {loading ? '创建中...' : '创建 Agent'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
