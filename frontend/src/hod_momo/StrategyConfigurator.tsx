import { useState } from 'react';
import type { StrategyConfig } from './types';
import { BoolField, ColorField, NumField } from './HodMomoConfigFields';

export function StrategyConfigurator({
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
      <label className="hod-cfg-check">
        <input
          type="checkbox"
          checked={cfg.requires_hod !== false}
          onChange={e => onChange({ requires_hod: e.target.checked })}
        />
        Require new HOD (off = Running Up style)
      </label>
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
