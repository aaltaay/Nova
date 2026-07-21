import { useMemo, useState } from 'react';
import type { AlertObject } from './types';
import type { UseHodMomoConfigReturn } from './useHodMomoConfig';
import { collapseAlertsBySymbol } from './collapseAlertsBySymbol';
import { HodMomoAlertTable } from './HodMomoAlertTable';
import { HodMomoDebugPanel } from './HodMomoDebugPanel';
import { HodMomoIntegrityBanner } from './HodMomoIntegrityBanner';
import {
  defaultHodMomentumVisibleStrategies,
  HOD_MOMENTUM_STRATEGY_META,
} from './scannerPartition';

type SubPanel = 'main' | 'debug';

function StrategyChipStrip({
  activeSubPanel,
  onSelectPanel,
  visibleStrategies,
  onToggleStrategy,
  counts,
  configColors,
}: {
  activeSubPanel: SubPanel;
  onSelectPanel: (panel: SubPanel) => void;
  visibleStrategies: Set<number>;
  onToggleStrategy: (id: number) => void;
  counts: Record<number, number>;
  configColors: Record<number, string>;
}) {
  return (
    <div className="hod-subpanel-strip" role="toolbar" aria-label="HOD Momentum strategy filters">
      <button
        type="button"
        className={`hod-subpanel-btn${activeSubPanel === 'main' ? ' active' : ''}`}
        onClick={() => onSelectPanel('main')}
      >
        Main feed
      </button>
      {HOD_MOMENTUM_STRATEGY_META.map(s => {
        const color = configColors[s.id] || s.color;
        const count = counts[s.id] ?? 0;
        const enabled = visibleStrategies.has(s.id);
        return (
          <button
            key={s.id}
            type="button"
            className={`hod-subpanel-btn hod-strategy-chip${enabled ? '' : ' hod-strategy-chip--off'}`}
            style={enabled ? { borderBottomColor: color } : undefined}
            onClick={() => {
              onSelectPanel('main');
              onToggleStrategy(s.id);
            }}
            title={enabled ? `Hide ${s.name}` : `Show ${s.name}`}
            aria-pressed={enabled}
          >
            <span
              className="hod-subpanel-dot"
              style={{
                background: enabled ? color : 'transparent',
                outline: `1px solid ${color}`,
              }}
            />
            <span className="hod-subpanel-label">{s.name}</span>
            {count > 0 && <span className="hod-subpanel-count">{count}</span>}
          </button>
        );
      })}
      <button
        type="button"
        className={`hod-subpanel-btn hod-subpanel-debug${activeSubPanel === 'debug' ? ' active' : ''}`}
        onClick={() => onSelectPanel('debug')}
        title="Debug panel — gate counters, decisions, symbol inspector"
      >
        Debug
      </button>
    </div>
  );
}

interface HodMomoTabProps {
  /** HOD Momentum alerts only (Running Up already partitioned out). */
  alerts: AlertObject[];
  totalToday?: number;
  connected: boolean;
  config: UseHodMomoConfigReturn;
  selectedSymbol: string | null;
  onSelectSymbol: (sym: string) => void;
  onOpenTrading: (sym: string) => void;
  onOpenSettings: () => void;
  onClearAlerts: () => void;
}

export function HodMomoTab({
  alerts,
  totalToday,
  connected,
  config,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  onOpenSettings,
  onClearAlerts,
}: HodMomoTabProps) {
  const [activeSubPanel, setActiveSubPanel] = useState<SubPanel>('main');
  const [visibleStrategies, setVisibleStrategies] = useState<Set<number>>(
    defaultHodMomentumVisibleStrategies,
  );

  const consolidationSec = config.state.master.consolidation_sec;

  const configColors = useMemo<Record<number, string>>(() => {
    const result: Record<number, string> = {};
    for (const [sid, cfg] of Object.entries(config.state.strategies)) {
      result[Number(sid)] = cfg.color;
    }
    return result;
  }, [config.state.strategies]);

  const strategyCounts = useMemo<Record<number, number>>(() => {
    const c: Record<number, number> = {};
    for (const a of alerts) {
      c[a.strategy_id] = (c[a.strategy_id] ?? 0) + 1;
    }
    return c;
  }, [alerts]);

  const visibleAlerts = useMemo(() => {
    const filtered = alerts.filter(a => visibleStrategies.has(a.strategy_id));
    return collapseAlertsBySymbol(filtered);
  }, [alerts, visibleStrategies]);

  function toggleStrategy(id: number) {
    setVisibleStrategies(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="hod-momo-tab">
      <div className="hod-header-bar">
        <div className="hod-header-left">
          <span className={`hod-connection-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span className="hod-header-title">HOD Momo Scanner</span>
          <span className="hod-alert-count">{totalToday ?? alerts.length} alerts today</span>
        </div>
        <div className="hod-header-right">
          <button
            type="button"
            className="hod-clear-btn"
            onClick={onClearAlerts}
            title="Clear today's HOD Momentum alerts (shared store with Running Up)"
          >
            Clear today
          </button>
          <button
            type="button"
            className="hod-settings-btn"
            onClick={onOpenSettings}
            title="Configure HOD Momentum strategies"
          >
            ⚙ Configure
          </button>
        </div>
      </div>

      <p className="hod-scanner-blurb">
        New high of day + momentum sub-strategies. Running Up is a separate tab.
      </p>

      <HodMomoIntegrityBanner />

      <StrategyChipStrip
        activeSubPanel={activeSubPanel}
        onSelectPanel={setActiveSubPanel}
        visibleStrategies={visibleStrategies}
        onToggleStrategy={toggleStrategy}
        counts={strategyCounts}
        configColors={configColors}
      />

      {activeSubPanel === 'debug' ? (
        <HodMomoDebugPanel
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
        />
      ) : (
        <HodMomoAlertTable
          alerts={visibleAlerts}
          connected={connected}
          consolidationSec={consolidationSec}
          configColors={configColors}
          strategyCounts={strategyCounts}
          visibleStrategies={visibleStrategies}
          onToggleStrategy={toggleStrategy}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={onSelectSymbol}
          onOpenTrading={onOpenTrading}
          filterableStrategies={HOD_MOMENTUM_STRATEGY_META}
        />
      )}
    </div>
  );
}
