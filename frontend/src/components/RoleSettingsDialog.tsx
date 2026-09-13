import { useEffect, useRef, useState } from 'react';
import { Settings, Save, Trash2, X } from 'lucide-react';

type Profile = { role_definition: string; system_prompt: string; evaluation_focus: string[] };
type Version = Profile & { id: string; created_at: string };
const roles = [['teacher', '教师'], ['student:high', '拓展型学生'], ['student:medium', '进阶型学生'], ['student:low', '基础型学生'], ['supervisor', '督导']];
const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export function RoleSettingsDialog({ runId }: { runId: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState('supervisor');
  const [draft, setDraft] = useState<Profile | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [requirement, setRequirement] = useState('');
  const path = `${base}/classroom/runs/${encodeURIComponent(runId)}/role-settings/${encodeURIComponent(role)}`;
  useEffect(() => {
    if (!open) return;
    let active = true;
    setDraft(null); setMessage('正在加载角色设置…');
    fetch(path).then(async response => {
      if (!response.ok) throw new Error('角色设置加载失败');
      return response.json();
    }).then(data => {
      if (active) { setDraft(data.profile); setVersions(data.versions); setMessage(''); }
    }).catch(error => { if (active) setMessage(String(error)); });
    return () => { active = false; };
  }, [path, open]);
  const mutate = async (method: string, suffix = '') => {
    setBusy(true);
    try {
      const response = await fetch(path + suffix, { method, headers: { 'Content-Type': 'application/json' }, ...(method === 'PUT' ? { body: JSON.stringify(draft) } : {}) });
      if (!response.ok) {
        // 后端会用 detail 说明具体原因(如「评价维度最多 12 条」)，透传它，
        // 否则教师只能看到「保存失败，请重试」而无法自行修正输入。
        const detail = await response.json().catch(() => null);
        const message = Array.isArray(detail?.errors) && detail.errors.length
          ? detail.errors.map((item: { loc?: unknown[]; msg?: string }) => `${(item.loc || []).slice(1).join('.')}: ${item.msg || ''}`).join('；')
          : detail?.detail;
        throw new Error(message ? String(message) : '保存或删除失败，请重试');
      }
      const data = await response.json();
      setVersions(data.versions);
      setMessage(method === 'PUT' ? '已导入最新提示词，将用于本课程该角色的下一次调用。' : '历史版本已删除，当前生效提示词保持不变。');
    } catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  };
  const generate = async () => {
    if (!requirement.trim()) return;
    setBusy(true); setMessage('AI 正在补充角色提示词…');
    try {
      const response = await fetch(`${path}/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ requirement, profile: draft }) });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || '提示词生成失败');
      setDraft(await response.json());
      setMessage('已生成补充草稿，请编辑确认后点击“保存并应用”。编排接口不会改变。');
    } catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  };
  return <div className="role-settings-entry">
    <button type="button" onClick={() => { setOpen(true); dialog.current?.showModal(); }}><Settings size={16} />智能体角色设置</button>
    <dialog ref={dialog} className="role-settings-dialog" onClose={() => setOpen(false)} onCancel={event => { if (busy) event.preventDefault(); }}>
      <header><strong>本课程角色与提示词</strong><button type="button" aria-label="关闭角色设置" disabled={busy} onClick={() => dialog.current?.close()}><X size={18} /></button></header>
      <div className="role-settings-body">
        <label>智能体<select disabled={busy} value={role} onChange={event => { if (window.confirm('切换角色将放弃尚未保存的编辑，继续吗？')) setRole(event.target.value); }}>{roles.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        {draft && <>
          <label>角色职责（当前保存的原文）<textarea disabled={busy} rows={3} maxLength={4000} value={draft.role_definition} onChange={event => setDraft({ ...draft, role_definition: event.target.value })} /></label>
          <label>{role === 'teacher' ? '讲解与反馈要求' : role === 'supervisor' ? '评价与证据要求' : '听课、提问与回答要求'}（当前保存的原文）<textarea disabled={busy} rows={7} maxLength={8000} value={draft.system_prompt} onChange={event => setDraft({ ...draft, system_prompt: event.target.value })} /></label>
          {role === 'supervisor' && <label>评价维度（每行一项）<textarea disabled={busy} rows={6} value={draft.evaluation_focus.join('\n')} onChange={event => setDraft({ ...draft, evaluation_focus: event.target.value.split('\n') })} /></label>}
          <section className="role-ai-assist"><h4>AI 补充提示词</h4><p>描述希望增加的性格、表达方式或行为倾向。AI 只生成可编辑文本，不修改课堂编排、动作协议和权限。</p><textarea disabled={busy} rows={3} placeholder="例如：基础型学生比较谨慎，遇到术语会先表达不确定，只有真正困惑时才提问。" value={requirement} onChange={event => setRequirement(event.target.value)} /><button type="button" disabled={busy || !requirement.trim()} onClick={() => void generate()}>生成详细提示词草稿</button></section>
          <p>以上为本课程可自定义配置原文。动作格式、发言权限及上下文隔离约束由系统单独提供，不包含在此编辑区。</p>
          <section><h4>最近 3 个保存版本</h4>{!versions.length && <p>暂无历史版本</p>}{versions.map(version => <div className="role-version" key={version.id}><time>{new Date(version.created_at).toLocaleString()}</time><button type="button" disabled={busy} onClick={() => { setDraft(version); setMessage('历史版本已载入编辑区，保存后生效。'); }}>载入编辑</button><button type="button" aria-label="删除历史版本" disabled={busy} onClick={() => { if (window.confirm('删除此历史版本？当前生效提示词不会改变。')) void mutate('DELETE', `/versions/${version.id}`); }}><Trash2 size={15} /></button></div>)}</section>
        </>}
        <p role="status">{message}</p>
      </div>
      <footer><span>仅用于当前课程；保存时保留最近 3 个版本。</span><button type="button" disabled={busy || !draft?.role_definition.trim() || !draft?.system_prompt.trim()} onClick={() => void mutate('PUT')}><Save size={15} />{busy ? '处理中…' : '保存并应用'}</button></footer>
    </dialog>
  </div>;
}
