import { useMemo, useState } from 'react';
import { HOD_MOMO_RUNNING_UP_STRATEGY_ID, STRATEGY_META } from '../constants';
import type { AlertObject } from './types';
import type { UseHodMomoConfigReturn } from './useHodMomoConfig';
import { collapseAlertsBySymbol } from './collapseAlertsBySymbol';
import { HodMomoAlertTable } from './HodMomoAlertTable';
import { HodMomoDebugPanel } from './HodMomoDebugPanel';
import { HodMomoIntegrityBanner } from './HodMomoIntegrityBanner';

type SubPanel = 'main' | 'debug';

function StrategyChipStrip({
  activeSubPanel,
  onSelectPanel,
  visibleStrategies,
  onToggleStrategy,
  onRunningUpOnly,
  counts,
  configColors,
}: {
  activeSubPanel: SubPanel;
  onSelectPanel: (panel: SubPanel) => void;
  visibleStrategies: Set<number>;
  onToggleStrategy: (id: number) => void;
  onRunningUpOnly: () => void;
  counts: Record<number, number>;
  configColors: Record<number, string>;
}) {
  const runningUpOnly =
    visibleStrategies.size === 1 && visibleStrategies.has(HOD_MOMO_RUNNING_UP_STRATEGY_ID);
  return (
    <div className="hod-subpanel-strip" role="toolbar" aria-label="HOD strategy filters">
      <button
        type="button"
        className={`hod-subpanel-btn${activeSubPanel === 'main' ? ' active' : ''}`}
        onClick={() => onSelectPanel('main')}
      >
        Main feed
      </button>
      <button
        type="button"
        className={`hod-subpanel-btn hod-strategy-chip${runningUpOnly ? ' active' : ''}`}
        onClick={() => {
          onSelectPanel('main');
          onRunningUpOnly();
        }}
        title={
          runningUpOnly
            ? 'Show all strategies'
            : 'Show Running Up only (Warrior parity — no new HOD required)'
        }
        aria-pressed={runningUpOnly}
      >
        Running Up only
      </button>
      {STRATEGY_META.map(s => {
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
            <span className="hod-subpanel-dot" style={{ background: enabled ? color : 'transparent', outline: `1px solid ${color}` }} />
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
  alerts: AlertObject[];
  /** Full-day alert count (may exceed alerts.length when UI is capped). */
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
    new Set(STRATEGY_META.map(s => s.id)),
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

  function toggleRunningUpOnly() {
    setVisibleStrategies(prev => {
      const only =
        prev.size === 1 && prev.has(HOD_MOMO_RUNNING_UP_STRATEGY_ID);
      if (only) return new Set(STRATEGY_META.map(s => s.id));
      return new Set([HOD_MOMO_RUNNING_UP_STRATEGY_ID]);
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
            className="hod-clear-btn"
            onClick={onClearAlerts}
            title="Clear today's HOD Momo alerts (history for other days is kept)"
          >
            Clear today
          </button>
          <button className="hod-settings-btn" onClick={onOpenSettings} title="Configure strategies">
            ⚙ Configure
          </button>
        </div>
      </div>

      <HodMomoIntegrityBanner />

      <StrategyChipStrip
        activeSubPanel={activeSubPanel}
        onSelectPanel={setActiveSubPanel}
        visibleStrategies={visibleStrategies}
        onToggleStrategy={toggleStrategy}
        onRunningUpOnly={toggleRunningUpOnly}
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
        />
      )}
    </div>
  );
}
