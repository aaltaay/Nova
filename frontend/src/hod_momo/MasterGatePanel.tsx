import type { MasterGateConfig } from './types';
import { BoolField, NumField } from './HodMomoConfigFields';

export function MasterGatePanel({
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
