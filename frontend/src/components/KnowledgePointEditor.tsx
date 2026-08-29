// KnowledgePointEditor.tsx - 候选知识点编辑器（受控组件）
import { useRef, useState } from 'react';
import { ListChecks, Pencil, Plus, Star, X } from 'lucide-react';
import type { KnowledgePoint } from '../types/workflow';
import './KnowledgePointEditor.css';

interface KnowledgePointEditorProps {
  points: KnowledgePoint[];
  onChange: (next: KnowledgePoint[]) => void;
}

const DEFAULT_CHAPTER = '课程材料';
const DEFAULT_DIFFICULTY = '中等';

function createPoint(title: string): KnowledgePoint {
  return {
    title: title.trim(),
    chapter: DEFAULT_CHAPTER,
    is_key_point: false,
    difficulty_level: DEFAULT_DIFFICULTY,
    keywords: [],
  };
}

function isDuplicateTitle(points: KnowledgePoint[], title: string, ignoreIndex?: number): boolean {
  const normalized = title.trim().toLowerCase();
  return points.some((point, index) => index !== ignoreIndex && point.title.trim().toLowerCase() === normalized);
}

export function KnowledgePointEditor({ points, onChange }: KnowledgePointEditorProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [draftTitle, setDraftTitle] = useState('');
  const addInputRef = useRef<HTMLInputElement>(null);

  const startEdit = (index: number) => {
    setEditingIndex(index);
    setEditingTitle(points[index]?.title ?? '');
  };

  const cancelEdit = () => setEditingIndex(null);

  const commitEdit = () => {
    if (editingIndex === null || editingIndex >= points.length) {
      setEditingIndex(null);
      return;
    }
    const title = editingTitle.trim();
    // 标题为空或与已有重复时忽略提交
    if (title && !isDuplicateTitle(points, title, editingIndex)) {
      onChange(points.map((point, index) => (index === editingIndex ? { ...point, title } : point)));
    }
    setEditingIndex(null);
  };

  const toggleKeyPoint = (index: number) => {
    onChange(points.map((point, i) => (i === index ? { ...point, is_key_point: !point.is_key_point } : point)));
  };

  const removePoint = (index: number) => {
    setEditingIndex(null);
    onChange(points.filter((_, i) => i !== index));
  };

  const addPoint = () => {
    const title = draftTitle.trim();
    // 空输入不添加；与已有重复时也不添加
    if (!title || isDuplicateTitle(points, title)) return;
    onChange([...points, createPoint(title)]);
    setDraftTitle('');
    addInputRef.current?.focus();
  };

  return (
    <section className="kp-editor" aria-label="候选知识点编辑器">
      <header className="kp-header">
        <div className="kp-title">
          <ListChecks size={15} />
          <h3>候选知识点</h3>
          <span className="kp-badge">{points.length}</span>
        </div>
        <p className="kp-hint">启动前可增删调整，AI 教师将围绕这些知识点授课</p>
      </header>

      {points.length === 0 ? (
        <div className="kp-empty">暂无可编辑的知识点，可在下方手动添加</div>
      ) : (
        <div className="kp-chips">
          {points.map((point, index) => {
            const editing = editingIndex === index;
            return (
              <div key={index} className={`kp-chip ${point.is_key_point ? 'is-key' : ''} ${editing ? 'is-editing' : ''}`}>
                <button
                  type="button"
                  className="kp-star"
                  onClick={() => toggleKeyPoint(index)}
                  title={point.is_key_point ? '取消重点' : '设为重点'}
                  aria-label={`${point.is_key_point ? '取消' : '设为'}重点：${point.title}`}
                  aria-pressed={point.is_key_point}
                >
                  <Star size={13} fill={point.is_key_point ? 'currentColor' : 'none'} />
                </button>
                {editing ? (
                  <input
                    className="kp-edit-input"
                    value={editingTitle}
                    onChange={(event) => setEditingTitle(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') commitEdit();
                      else if (event.key === 'Escape') cancelEdit();
                    }}
                    onBlur={commitEdit}
                    autoFocus
                    aria-label={`编辑知识点标题：${point.title}`}
                  />
                ) : (
                  <span className="kp-chip-title" title={point.title}>{point.title}</span>
                )}
                <button
                  type="button"
                  className="kp-action"
                  onClick={() => startEdit(index)}
                  title="编辑标题"
                  aria-label={`编辑标题：${point.title}`}
                >
                  <Pencil size={12} />
                </button>
                <button
                  type="button"
                  className="kp-action kp-remove"
                  onClick={() => removePoint(index)}
                  title="删除知识点"
                  aria-label={`删除知识点：${point.title}`}
                >
                  <X size={13} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="kp-add">
        <input
          ref={addInputRef}
          className="kp-add-input"
          value={draftTitle}
          onChange={(event) => setDraftTitle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              addPoint();
            }
          }}
          placeholder="输入新知识点标题…"
          aria-label="新知识点标题"
        />
        <button
          type="button"
          className="kp-add-btn"
          onClick={addPoint}
          disabled={!draftTitle.trim()}
          title="添加知识点"
          aria-label="添加知识点"
        >
          <Plus size={13} />
          添加知识点
        </button>
      </div>
    </section>
  );
}
