import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL, STRATEGY_META } from '../constants';
import type { MasterGateConfig, StrategyConfig } from './types';
import type { UseHodMomoConfigReturn } from './useHodMomoConfig';

const API = `${API_BASE_URL}/api`;

// ── Small field helpers ───────────────────────────────────────────────────────

function NumField({
  label,
  value,
  onChange,
  step = 0.1,
  min = 0,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  hint?: string;
}) {
  return (
    <div className="hod-cfg-field">
      <label className="hod-cfg-label" title={hint}>{label}</label>
      <input
        className="hod-cfg-input"
        type="number"
        step={step}
        min={min}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
    </div>
  );
}

function BoolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="hod-cfg-toggle">
      <input type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="hod-cfg-field hod-cfg-field--color">
      <label className="hod-cfg-label">{label}</label>
      <input
        type="color"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="hod-cfg-color"
      />
      <span className="hod-cfg-color-hex">{value}</span>
    </div>
  );
}

// ── Strategy configurator panel ───────────────────────────────────────────────

function StrategyConfigurator({
  cfg,
  onChange,
  onReset,
}: {
  cfg: StrategyConfig;
  onChange: (patch: Partial<StrategyConfig>) => void;
  onReset: () => void;
}) {
  const [momoInput, setMomoInput] = useState('');

  function addMomo() {
    const sym = momoInput.trim().toUpperCase();
    if (!sym || cfg.former_momo_list.includes(sym)) return;
    onChange({ former_momo_list: [...cfg.former_momo_list, sym] });
    setMomoInput('');
  }

  function removeMomo(sym: string) {
    onChange({ former_momo_list: cfg.former_momo_list.filter(s => s !== sym) });
  }

  return (
    <div className="hod-strategy-cfg">
      <div className="hod-cfg-section-header">
        <span className="hod-cfg-section-title">Strategy Settings</span>
        <button className="hod-cfg-reset-btn" onClick={onReset}>Reset to Defaults</button>
      </div>

      <div className="hod-cfg-row">
        <BoolField label="Enabled" value={cfg.enabled} onChange={v => onChange({ enabled: v })} />
        <BoolField label="Audio Alert" value={cfg.audio} onChange={v => onChange({ audio: v })} />
      </div>

      <ColorField label="Color" value={cfg.color} onChange={v => onChange({ color: v })} />

      <div className="hod-cfg-section">Price Filter (0 = disabled)</div>
      <div className="hod-cfg-row">
        <NumField label="Min Price $" value={cfg.min_price} onChange={v => onChange({ min_price: v })} step={0.01} />
        <NumField label="Max Price $" value={cfg.max_price} onChange={v => onChange({ max_price: v })} step={0.01} />
      </div>

      <div className="hod-cfg-section">Float Filter (0 = disabled)</div>
      <div className="hod-cfg-row">
        <NumField label="Min Float" value={cfg.min_float} onChange={v => onChange({ min_float: v })} step={100000} hint="shares" />
        <NumField label="Max Float" value={cfg.max_float} onChange={v => onChange({ max_float: v })} step={100000} hint="shares" />
      </div>

      <div className="hod-cfg-section">Volume / RVOL (0 = disabled)</div>
      <div className="hod-cfg-row">
        <NumField label="Min Volume" value={cfg.min_volume} onChange={v => onChange({ min_volume: v })} step={1000} />
        <NumField label="Min RVOL" value={cfg.min_rvol} onChange={v => onChange({ min_rvol: v })} step={0.1} />
        <NumField label="Max RVOL" value={cfg.max_rvol} onChange={v => onChange({ max_rvol: v })} step={0.1} />
      </div>

      <div className="hod-cfg-section">Gap % Filter (0 = disabled)</div>
      <div className="hod-cfg-row">
        <NumField label="Min Gap %" value={cfg.min_gap_pct} onChange={v => onChange({ min_gap_pct: v })} step={0.5} />
        <NumField label="Max Gap %" value={cfg.max_gap_pct} onChange={v => onChange({ max_gap_pct: v })} step={0.5} />
      </div>

      <div className="hod-cfg-section">Change % Filter (0 = disabled)</div>
      <div className="hod-cfg-row">
        <NumField label="Min Change %" value={cfg.min_change_pct} onChange={v => onChange({ min_change_pct: v })} step={0.5} />
        <NumField label="Max Change %" value={cfg.max_change_pct} onChange={v => onChange({ max_change_pct: v })} step={0.5} />
      </div>

      <div className="hod-cfg-section">Squeeze / Momentum (0 = disabled)</div>
      <div className="hod-cfg-row">
        <NumField label="Surge %" value={cfg.surge_pct} onChange={v => onChange({ surge_pct: v })} step={0.5} />
        <NumField label="Surge Window (min)" value={cfg.surge_window_min} onChange={v => onChange({ surge_window_min: Math.round(v) })} step={1} />
      </div>
      <div className="hod-cfg-row">
        <div className="hod-cfg-field">
          <label className="hod-cfg-label">Measurement Method</label>
          <select
            className="hod-cfg-select"
            value={cfg.surge_method}
            onChange={e => onChange({ surge_method: e.target.value as 'low_to_current' | 'fixed_start' })}
          >
            <option value="low_to_current">Low-to-Current (default)</option>
            <option value="fixed_start">Fixed-Start</option>
          </select>
        </div>
      </div>

      <div className="hod-cfg-section">52-Week High (0 = disabled)</div>
      <NumField
        label="Proximity to 52wk High %"
        value={cfg.proximity_52wk_pct}
        onChange={v => onChange({ proximity_52wk_pct: v })}
        step={0.5}
        hint="e.g. 5 = within 5% of the 52wk high"
      />

      <div className="hod-cfg-section">Former Momo List</div>
      <div className="hod-momo-list">
        {cfg.former_momo_list.map(sym => (
          <span key={sym} className="hod-momo-tag">
            {sym}
            <button className="hod-momo-tag-remove" onClick={() => removeMomo(sym)}>×</button>
          </span>
        ))}
      </div>
      <div className="hod-momo-add-row">
        <input
          className="hod-cfg-input hod-momo-input"
          type="text"
          value={momoInput}
          onChange={e => setMomoInput(e.target.value.toUpperCase())}
          placeholder="Add ticker…"
          onKeyDown={e => e.key === 'Enter' && addMomo()}
        />
        <button className="hod-cfg-btn" onClick={addMomo}>Add</button>
      </div>

      <div className="hod-cfg-section">Notes</div>
      <textarea
        className="hod-cfg-textarea"
        value={cfg.notes}
        onChange={e => onChange({ notes: e.target.value })}
        placeholder="Document your tuning, e.g. what worked, what to adjust…"
        rows={3}
      />
    </div>
  );
}

// ── Master gate panel ─────────────────────────────────────────────────────────

function MasterGatePanel({
  master,
  onChange,
}: {
  master: MasterGateConfig;
  onChange: (patch: Partial<MasterGateConfig>) => void;
}) {
  return (
    <div className="hod-master-cfg">
      <div className="hod-cfg-section-header">
        <span className="hod-cfg-section-title">Master Gate</span>
      </div>
      <BoolField
        label="Require New HOD (price must be at or above session high)"
        value={master.hod_required}
        onChange={v => onChange({ hod_required: v })}
      />
      <div className="hod-cfg-row">
        <NumField label="Momentum Surge %" value={master.surge_pct} onChange={v => onChange({ surge_pct: v })} step={0.5} />
        <NumField label="Surge Lookback (min)" value={master.surge_window_min} onChange={v => onChange({ surge_window_min: Math.round(v) })} step={1} />
      </div>
      <NumField label="Minimum RVOL" value={master.min_rvol} onChange={v => onChange({ min_rvol: v })} step={0.1} />
      <div className="hod-cfg-section">Session RVOL Overrides</div>
      <div className="hod-cfg-row">
        <NumField label="Pre-market Min RVOL" value={master.premarket_min_rvol} onChange={v => onChange({ premarket_min_rvol: v })} step={0.1} />
        <NumField label="After-hours Min RVOL" value={master.afterhours_min_rvol} onChange={v => onChange({ afterhours_min_rvol: v })} step={0.1} />
      </div>
      <div className="hod-cfg-section">Timing</div>
      <div className="hod-cfg-row">
        <NumField label="Cooldown (sec)" value={master.cooldown_sec} onChange={v => onChange({ cooldown_sec: v })} step={5} />
        <NumField label="Consolidation Window (sec)" value={master.consolidation_sec} onChange={v => onChange({ consolidation_sec: v })} step={1} />
      </div>
    </div>
  );
}

// ── Blocklist panel ───────────────────────────────────────────────────────────

function BlocklistPanel() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [input, setInput] = useState('');

  useEffect(() => {
    fetch(`${API}/hod-momo/blocklist`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.symbols) setSymbols(data.symbols); })
      .catch(() => {});
  }, []);

  const add = useCallback(() => {
    const sym = input.trim().toUpperCase();
    if (!sym || symbols.includes(sym)) return;
    fetch(`${API}/hod-momo/blocklist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: sym }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.symbols) setSymbols(data.symbols); });
    setInput('');
  }, [input, symbols]);

  const remove = useCallback((sym: string) => {
    fetch(`${API}/hod-momo/blocklist/${sym}`, { method: 'DELETE' })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.symbols) setSymbols(data.symbols); });
  }, []);

  return (
    <div className="hod-blocklist-panel">
      <div className="hod-cfg-section-header">
        <span className="hod-cfg-section-title">Global Blocklist</span>
      </div>
      <p className="hod-cfg-hint">Blocked tickers are excluded from all HOD Momo strategy evaluations.</p>
      <div className="hod-momo-list">
        {symbols.map(sym => (
          <span key={sym} className="hod-momo-tag hod-block-tag">
            {sym}
            <button className="hod-momo-tag-remove" onClick={() => remove(sym)}>×</button>
          </span>
        ))}
        {symbols.length === 0 && <span className="na-muted">No blocked tickers</span>}
      </div>
      <div className="hod-momo-add-row">
        <input
          className="hod-cfg-input hod-momo-input"
          type="text"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          placeholder="Ticker to block…"
          onKeyDown={e => e.key === 'Enter' && add()}
        />
        <button className="hod-cfg-btn" onClick={add}>Block</button>
      </div>
    </div>
  );
}

// ── Main Settings Drawer ──────────────────────────────────────────────────────

interface HodMomoSettingsProps {
  config: UseHodMomoConfigReturn;
  onClose: () => void;
}

export function HodMomoSettings({ config, onClose }: HodMomoSettingsProps) {
  const [selectedStrategy, setSelectedStrategy] = useState<number>(1);
  const [activeSection, setActiveSection] = useState<'strategy' | 'master' | 'blocklist'>('strategy');

  const { state, updateStrategy, updateMaster, resetStrategy, resetAll } = config;
  const cfg = state.strategies[String(selectedStrategy)];

  return (
    <div className="hod-settings-drawer">
      <div className="hod-settings-header">
        <span className="hod-settings-title">HOD Momo Configurator</span>
        <button className="hod-settings-close" onClick={onClose}>✕</button>
      </div>

      <div className="hod-settings-tabs">
        <button
          className={`hod-settings-tab${activeSection === 'strategy' ? ' active' : ''}`}
          onClick={() => setActiveSection('strategy')}
        >
          Strategies
        </button>
        <button
          className={`hod-settings-tab${activeSection === 'master' ? ' active' : ''}`}
          onClick={() => setActiveSection('master')}
        >
          Master Gate
        </button>
        <button
          className={`hod-settings-tab${activeSection === 'blocklist' ? ' active' : ''}`}
          onClick={() => setActiveSection('blocklist')}
        >
          Blocklist
        </button>
      </div>

      <div className="hod-settings-body">
        {activeSection === 'strategy' && (
          <>
            <div className="hod-strategy-selector">
              <label className="hod-cfg-label">Strategy</label>
              <select
                className="hod-cfg-select"
                value={selectedStrategy}
                onChange={e => setSelectedStrategy(Number(e.target.value))}
              >
                {STRATEGY_META.map(s => (
                  <option key={s.id} value={s.id}>{s.id}. {s.name}</option>
                ))}
              </select>
            </div>
            {cfg ? (
              <StrategyConfigurator
                cfg={cfg}
                onChange={patch => updateStrategy(selectedStrategy, patch)}
                onReset={() => resetStrategy(selectedStrategy)}
              />
            ) : (
              <div className="hod-cfg-hint">Loading strategy config…</div>
            )}
            <div className="hod-settings-global-actions">
              <button
                className="hod-cfg-btn hod-cfg-btn--danger"
                onClick={() => { if (window.confirm('Reset ALL strategies and master gate to defaults?')) resetAll(); }}
              >
                Reset All Strategies
              </button>
            </div>
          </>
        )}

        {activeSection === 'master' && (
          <MasterGatePanel
            master={state.master}
            onChange={updateMaster}
          />
        )}

        {activeSection === 'blocklist' && <BlocklistPanel />}
      </div>
    </div>
  );
}
