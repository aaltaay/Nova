import { useState } from 'react';
import { APP_DIALOG_RESET_LABEL, STRATEGY_META } from '../constants';
import { confirmApp } from '../ux';
import { BlocklistPanel } from './BlocklistPanel';
import { MasterGatePanel } from './MasterGatePanel';
import { StrategyConfigurator } from './StrategyConfigurator';
import type { UseHodMomoConfigReturn } from './useHodMomoConfig';

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
                onClick={() => {
                  void confirmApp({
                    title: 'Reset all strategies?',
                    message: 'Reset ALL strategies and master gate to defaults?',
                    confirmLabel: APP_DIALOG_RESET_LABEL,
                    tone: 'danger',
                  }).then(ok => {
                    if (ok) resetAll();
                  });
                }}
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
