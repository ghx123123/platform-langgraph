import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Eye,
  EyeOff,
  History,
  Loader2,
  PlugZap,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  X,
} from 'lucide-react';
import { getErrorMessage, modelSettingsApi } from '../lib/api';
import type {
  ModelDiscoveryResult,
  ModelHistoryItem,
  ModelSettingsInput,
  ModelSettings,
  ModelTestResult,
} from '../types/workflow';

interface Props { onClose: () => void; onSaved: () => void; }

const emptyForm: ModelSettingsInput = {
  provider: 'mock',
  base_url: 'https://api.openai.com/v1',
  model: 'deterministic-mock',
  api_key: '',
  temperature: 0.2,
  timeout_seconds: 90,
};

const mockModels = ['deterministic-mock', 'mock-teaching', 'mock-fast'];

// 厂商预设: 选厂商自动填接口地址(用户只需填 API Key + 选模型)
const VENDOR_PRESETS: Array<{ name: string; base_url: string; models: string[]; hint: string }> = [
  { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', models: ['deepseek-v4-flash', 'deepseek-v3'], hint: '适合 dsh 智能体（openai 兼容）' },
  { name: 'MiniMax', base_url: 'https://api.minimaxi.com/v1', models: ['minimax-m3', 'minimax-m2.7'], hint: 'MiniMax 官方接口' },
  { name: 'OpenAI', base_url: 'https://api.openai.com/v1', models: ['gpt-4.1-mini', 'gpt-4o'], hint: 'OpenAI 官方接口' },
  { name: '自定义', base_url: '', models: [], hint: '手动填写接口地址' },
];

function normalizeUrl(value: string): string {
  return value.trim().replace(/\/+$/, '');
}

function formatHistoryDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function getProviderLabel(provider: ModelHistoryItem['provider']): string {
  return provider === 'mock' ? '本地演示' : provider === 'dsh' ? 'dsh 智能体' : 'OpenAI 兼容';
}

export function ModelSettingsPanel({ onClose, onSaved }: Props) {
  const [form, setForm] = useState<ModelSettingsInput>(emptyForm);
  const [vendor, setVendor] = useState('DeepSeek');
  const [history, setHistory] = useState<ModelHistoryItem[]>([]);
  const [hasKey, setHasKey] = useState(false);
  const [savedEndpoint, setSavedEndpoint] = useState<Pick<ModelSettings, 'provider' | 'base_url'> | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'discover' | 'test' | 'save' | null>(null);
  const [discovery, setDiscovery] = useState<ModelDiscoveryResult | null>(null);
  const [result, setResult] = useState<ModelTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const visibleHistory = useMemo(
    () => history.filter((item, index, items) => items.findIndex((other) => (
      other.provider === item.provider
      && other.model === item.model
      && (item.provider === 'mock' || other.base_url === item.base_url)
    )) === index).slice(0, 6),
    [history],
  );

  useEffect(() => {
    let active = true;
    Promise.all([modelSettingsApi.get(), modelSettingsApi.history()])
      .then(([value, items]) => {
        if (!active) return;
        setForm({
          provider: value.provider,
          base_url: value.base_url,
          model: value.model,
          temperature: value.temperature,
          timeout_seconds: value.timeout_seconds,
          api_key: '',
        });
        setHistory(items);
        setHasKey(value.has_api_key);
        setSavedEndpoint({ provider: value.provider, base_url: value.base_url });
        // 厂商高亮跟随当前已保存的接口地址
        const match = VENDOR_PRESETS.find((v) => v.base_url && value.base_url && normalizeUrl(v.base_url) === normalizeUrl(value.base_url));
        if (match) setVendor(match.name);
      })
      .catch((reason) => { if (active) setError(getErrorMessage(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const update = <K extends keyof ModelSettingsInput>(key: K, value: ModelSettingsInput[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    if (key === 'provider' || key === 'base_url' || key === 'api_key') setDiscovery(null);
    setResult(null);
    setError(null);
  };

  const changeProvider = (provider: ModelSettingsInput['provider']) => {
    setForm((current) => ({
      ...current,
      provider,
      model: provider === 'mock' ? 'deterministic-mock' : provider === 'dsh' ? (['minimax-m3', 'minimax-m2.7', 'deepseek-v4-flash'].includes(current.model) ? current.model : 'deepseek-v4-flash') : mockModels.includes(current.model) ? 'gpt-4.1-mini' : current.model,
      api_key: provider === 'mock' ? '' : current.api_key,
    }));
    setDiscovery(null);
    setResult(null);
    setError(null);
  };

  // 选厂商 → 自动填接口地址(和推荐模型), 用户只需填 API Key
  const applyVendor = (name: string) => {
    const preset = VENDOR_PRESETS.find((p) => p.name === name) || VENDOR_PRESETS[VENDOR_PRESETS.length - 1];
    setVendor(preset.name);
    setForm((current) => {
      const next: ModelSettingsInput = { ...current, base_url: preset.base_url };
      const isDsh = current.provider === 'dsh';
      const isMock = current.provider === 'mock';
      if (preset.models.length && !isMock) {
        // 优先匹配 dsh 的桥路由模型名(deepseek-v4-flash/minimax-m3), 保证 dsh 可用
        const preferred = isDsh ? (preset.models.find((m) => ['minimax-m3', 'minimax-m2.7', 'deepseek-v4-flash'].includes(m)) || preset.models[0]) : preset.models[0];
        next.model = preferred;
      } else if (!preset.base_url) {
        next.model = current.model;
      }
      return next;
    });
    setDiscovery(null);
    setResult(null);
    setError(null);
  };

  const applyHistory = (item: ModelHistoryItem) => {
    setForm((current) => ({
      ...current,
      provider: item.provider,
      base_url: item.base_url,
      model: item.model,
      api_key: '',
    }));
    setDiscovery(null);
    setResult(null);
    setError(null);
  };

  const savedKeyCanBeRetained = Boolean(
    hasKey
      && savedEndpoint
      && form.provider === savedEndpoint.provider
      && normalizeUrl(form.base_url) === normalizeUrl(savedEndpoint.base_url),
  );

  const discover = async () => {
    setBusy('discover');
    setError(null);
    setResult(null);
    setDiscovery(null);
    // 所有 provider(含 dsh)都真实调官网 /models 探测; dsh 由后端带面板 key 请求,
    // 未填 key 时后端回退环境变量 key; 若真无 key 会返回 401 等明确信息。
    try {
      setDiscovery(await modelSettingsApi.discover(form));
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setBusy('test');
    setError(null);
    setResult(null);
    try {
      setResult(await modelSettingsApi.test(form));
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    setBusy('save');
    setError(null);
    try {
      const saved = await modelSettingsApi.update(form);
      setHasKey(saved.has_api_key);
      setSavedEndpoint({ provider: saved.provider, base_url: saved.base_url });
      setForm((current) => ({ ...current, api_key: '' }));
      onSaved();
      onClose();
    } catch (reason) {
      setError(getErrorMessage(reason));
    } finally {
      setBusy(null);
    }
  };

  const connectionState = discovery ? (discovery.ok ? 'connected' : 'failed') : 'idle';
  const selectableModels = discovery?.ok ? discovery.models : (form.provider === 'dsh' ? ['deepseek-v4-flash', 'minimax-m3', 'minimax-m2.7'] : []);
  const selectedDiscoveredModel = selectableModels.includes(form.model) ? form.model : '';

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <header className="dialog-header">
          <div className="dialog-title">
            <span className="dialog-icon"><Settings2 size={18} /></span>
            <div><h2 id="settings-title">模型服务设置</h2><p>选择模型、探测接口并保留最近使用记录</p></div>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭设置" aria-label="关闭设置"><X size={17} /></button>
        </header>
        {loading ? <div className="settings-loading"><Loader2 className="spin" size={20} />正在读取配置</div> : (
          <div className="settings-body">
            <section className="settings-section settings-connection">
              <div className="settings-section-heading">
                <div><strong>连接来源</strong><small>先确认接口可达，再从返回列表中选择模型</small></div>
                <span className={`connection-state ${connectionState}`}>
                  {connectionState === 'connected' && <CheckCircle2 size={13} />}
                  {connectionState === 'failed' && <AlertCircle size={13} />}
                  {connectionState === 'idle' && <PlugZap size={13} />}
                  {connectionState === 'connected' ? '已连接' : connectionState === 'failed' ? '连接失败' : '未检测'}
                </span>
              </div>
              <div className="field-group">
                <span className="field-label">服务类型</span>
                <div className="provider-control">
                  <button type="button" className={form.provider === 'mock' ? 'active' : ''} onClick={() => changeProvider('mock')}>本地演示模型</button>
                  <button type="button" className={form.provider === 'dsh' ? 'active' : ''} onClick={() => changeProvider('dsh')}>dsh 智能体</button>
                  <button type="button" className={form.provider === 'openai_compatible' ? 'active' : ''} onClick={() => changeProvider('openai_compatible')}>OpenAI 兼容接口</button>
                </div>
              </div>
              {form.provider !== 'mock' && <>
                <div className="field-group">
                  <span className="field-label">模型提供方 <small>选择后自动填写接口地址</small></span>
                  <div className="provider-control vendor-control">
                    {VENDOR_PRESETS.map((preset) => <button type="button" key={preset.name} className={vendor === preset.name ? 'active' : ''} onClick={() => applyVendor(preset.name)} title={preset.hint}>{preset.name}</button>)}
                  </div>
                </div>
              </>}
              <div className="endpoint-row">
                <label className="field-group"><span className="field-label">接口地址</span><input value={form.base_url} onChange={(event) => update('base_url', event.target.value)} disabled={form.provider === 'mock'} placeholder="https://api.openai.com/v1" /></label>
                <button className="secondary-button discover-button" type="button" onClick={() => void discover()} disabled={Boolean(busy) || loading}>
                  {busy === 'discover' ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
                  {busy === 'discover' ? '连接中' : form.provider === 'mock' ? '查看模型' : '连接并获取模型'}
                </button>
              </div>
              {discovery && <div className={`discovery-meta ${discovery.ok ? 'ok' : 'failed'}`}><span>{discovery.message}</span><small>{discovery.latency_ms} ms</small></div>}
            </section>

            <section className="settings-section">
              <div className="settings-section-heading"><div><strong>模型选择</strong><small>可选择接口发现的模型，也可以手动输入名称</small></div><span className="model-count">{discovery?.ok ? `${discovery.models.length} 个可用` : '等待连接'}</span></div>
              <div className="model-picker">
                <select value={selectedDiscoveredModel} onChange={(event) => event.target.value && update('model', event.target.value)} disabled={!discovery?.ok || Boolean(busy)} aria-label="选择已发现的模型">
                  <option value="">从接口返回列表中选择</option>
                  {selectableModels.length ? selectableModels.map((model) => <option key={model} value={model}>{model}</option>) : discovery?.ok && discovery.models.length === 0 && <option value="">暂无模型</option>}
                </select>
                <label className="field-group"><span className="field-label">当前模型</span><input value={form.model} onChange={(event) => update('model', event.target.value)} placeholder={form.provider === 'dsh' ? '例如 minimax-m3' : '例如 gpt-4.1-mini'} /></label>
              </div>
              {discovery?.ok && discovery.models.length > 0 && !selectedDiscoveredModel && <p className="field-hint">当前输入的模型不在本次返回列表中，保存前请确认名称。</p>}
              {form.provider === 'dsh' && <p className="field-hint" style={{ marginTop: 4, lineHeight: 1.6 }}>dsh 智能体模型切换即时生效，无需重启。若报「模型额度不足（429 限流）」请切换模型或给当前模型充值。</p>}
            </section>

            <label className="field-group">
              <span className="field-label">API Key <small>{form.provider === 'mock' ? '本地演示无需密钥' : savedKeyCanBeRetained ? '已配置，留空保留' : '必填：输入模型 API Key'}</small></span>
              <span className="secret-input"><input type={showKey ? 'text' : 'password'} value={form.api_key} onChange={(event) => update('api_key', event.target.value)} disabled={form.provider === 'mock'} placeholder={savedKeyCanBeRetained ? '••••••••••••••••' : '输入 API Key'} /><button type="button" onClick={() => setShowKey((value) => !value)} disabled={form.provider === 'mock'} title={showKey ? '隐藏' : '显示'} aria-label={showKey ? '隐藏 API Key' : '显示 API Key'}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></span>
            </label>

            <section className="settings-section history-section">
              <div className="settings-section-heading"><div><strong><History size={14} />最近使用</strong><small>只保存供应商、地址和模型名，不保存 API Key</small></div><span className="model-count">{history.length}/20</span></div>
              {visibleHistory.length > 0 ? <div className="model-history-list">
                {visibleHistory.map((item) => <button className="model-history-item" type="button" key={`${item.provider}-${item.base_url}-${item.model}`} onClick={() => applyHistory(item)} title={`使用 ${item.model}`}>
                  <span className="history-item-main"><strong translate="no">{item.model}</strong><small translate="no">{item.provider === 'mock' ? '本地演示服务 · 无需 API Key' : `${getProviderLabel(item.provider)} · ${item.provider === 'dsh' ? '本机 DeepSeek Harness' : item.base_url}`}</small></span>
                  <span className="history-item-meta"><small>{item.use_count} 次</small><small>{formatHistoryDate(item.last_used_at)}</small></span>
                  {item.has_api_key && <ShieldCheck size={14} aria-label="该模型最近使用时已配置密钥" />}
                </button>)}
              </div> : <div className="history-empty"><Clock3 size={15} /><span>保存模型后，会在这里快速切换</span></div>}
            </section>

            <div className="settings-grid">
              <label className="field-group"><span className="field-label">温度 <strong>{form.temperature.toFixed(1)}</strong></span><input type="range" min="0" max="2" step="0.1" value={form.temperature} onChange={(event) => update('temperature', Number(event.target.value))} /></label>
              <label className="field-group"><span className="field-label">超时时间（秒）</span><input type="number" min="5" max="600" value={form.timeout_seconds} onChange={(event) => update('timeout_seconds', Number(event.target.value))} /></label>
            </div>
            {result && <div className={`test-result ${result.ok ? 'success' : 'error'}`}>{result.ok ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}<span>{result.message}</span><small>{result.model} · {result.latency_ms} ms</small></div>}
            {error && <div className="test-result error"><AlertCircle size={16} /><span>{error}</span></div>}
          </div>
        )}
        <footer className="dialog-footer">
          <button className="secondary-button" type="button" onClick={() => void test()} disabled={Boolean(busy) || loading}><PlugZap size={15} />{busy === 'test' ? '检测中' : '测试连接'}</button>
          <button className="primary-button compact" type="button" onClick={() => void save()} disabled={Boolean(busy) || loading}><Save size={15} />{busy === 'save' ? '保存中' : '保存并应用'}</button>
        </footer>
      </section>
    </div>
  );
}
