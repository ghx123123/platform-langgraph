import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Clock3, KeyRound, Loader2, Settings2, Sparkles, Thermometer } from 'lucide-react';
import { getErrorMessage, modelSettingsApi } from '../lib/api';
import type { ModelHistoryItem, ModelSettings } from '../types/workflow';

interface Props {
  settings: ModelSettings | null;
  refreshKey: number;
  onChanged: (settings: ModelSettings) => void;
  onOpenSettings: () => void;
}

function sameEndpoint(settings: ModelSettings, item: ModelHistoryItem): boolean {
  if (settings.provider === 'dsh' && item.provider === 'dsh') return true;
  return settings.provider === item.provider && settings.base_url.replace(/\/+$/, '') === item.base_url.replace(/\/+$/, '');
}

export function ModelQuickSwitcher({ settings, refreshKey, onChanged, onOpenSettings }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<ModelHistoryItem[]>([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    modelSettingsApi.history().then((items) => { if (active) setHistory(items); }).catch(() => undefined);
    return () => { active = false; };
  }, [refreshKey]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const recent = useMemo(() => history.filter((item, index, items) => items.findIndex((other) => other.provider === item.provider && other.model === item.model && (item.provider === 'mock' || item.provider === 'dsh' || other.base_url === item.base_url)) === index).slice(0, 6), [history]);
  const switchModel = async (item: ModelHistoryItem) => {
    if (!settings || (!sameEndpoint(settings, item) && item.provider !== 'mock' && item.provider !== 'dsh')) { setOpen(false); onOpenSettings(); return; }
    setBusy(item.model); setError('');
    try {
      const next = await modelSettingsApi.update({ provider: item.provider, base_url: item.base_url, model: item.model, api_key: '', temperature: settings.temperature, timeout_seconds: settings.timeout_seconds });
      onChanged(next); setOpen(false);
    } catch (reason) { setError(getErrorMessage(reason)); }
    finally { setBusy(''); }
  };

  return <div className="model-quick-switcher" ref={rootRef}>
    <button type="button" className="model-quick-trigger" onClick={() => setOpen((value) => !value)} aria-expanded={open} title="替换当前模型"><Sparkles size={16} /><span><small>当前模型</small><strong translate="no">{settings?.provider === 'mock' ? '本地演示模型' : settings?.provider === 'dsh' ? 'dsh · ' : ''}{settings?.model || '读取中'}</strong></span><ChevronDown size={15} /></button>
    {open && <div className="model-quick-menu" role="dialog" aria-label="替换模型">
      <header><div><strong>替换模型</strong><small>选择同一接口下的模型可立即生效</small></div><button type="button" onClick={() => { setOpen(false); onOpenSettings(); }}><Settings2 size={15} />连接与参数设置</button></header>
      {recent.length ? <div className="model-quick-list">{recent.map((item) => { const current = Boolean(settings?.model === item.model && settings && sameEndpoint(settings, item)); const direct = Boolean(settings && (sameEndpoint(settings, item) || item.provider === 'mock' || item.provider === 'dsh')); return <button type="button" key={`${item.provider}-${item.base_url}-${item.model}`} onClick={() => void switchModel(item)} disabled={!!busy} aria-current={current ? 'true' : undefined}><span className="model-quick-name"><strong translate="no">{item.model}</strong><em className={current ? 'current' : direct ? 'direct' : 'configure'}>{current ? '当前使用' : direct ? '可直接切换' : '需配置连接'}</em></span><span className="model-quick-endpoint"><KeyRound size={13} /><small translate="no">{item.provider === 'mock' ? '本地演示服务，无需 API Key' : item.provider === 'dsh' ? '本机 DeepSeek Harness 智能体' : item.base_url}</small></span>{busy === item.model ? <Loader2 className="spin" size={16} /> : current ? <Check size={16} /> : <ChevronDown className="model-item-arrow" size={14} />}</button>; })}</div> : <p>暂无历史模型，请打开连接与参数设置添加。</p>}
      {settings && <footer><span><Thermometer size={14} />温度 <strong>{settings.temperature.toFixed(1)}</strong></span><span><Clock3 size={14} />超时 <strong>{settings.timeout_seconds} 秒</strong></span><button type="button" onClick={() => { setOpen(false); onOpenSettings(); }}>修改参数</button></footer>}
      {error && <em>{error}</em>}
    </div>}
  </div>;
}
