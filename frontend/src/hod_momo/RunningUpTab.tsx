import { useMemo } from 'react';
import {
  HOD_MOMO_RUNNING_UP_STRATEGY_ID,
  STRATEGY_META_MAP,
} from '../constants';
import type { AlertObject } from './types';
import type { UseHodMomoConfigReturn } from './useHodMomoConfig';
import { collapseAlertsBySymbol } from './collapseAlertsBySymbol';
import { HodMomoAlertTable } from './HodMomoAlertTable';

interface RunningUpTabProps {
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

/** Warrior-style sibling scanner — surge/RVOL without requiring a new HOD. */
export function RunningUpTab({
  alerts,
  totalToday,
  connected,
  config,
  selectedSymbol,
  onSelectSymbol,
  onOpenTrading,
  onOpenSettings,
  onClearAlerts,
}: RunningUpTabProps) {
  const consolidationSec = config.state.master.consolidation_sec;
  const meta = STRATEGY_META_MAP[HOD_MOMO_RUNNING_UP_STRATEGY_ID];

  const configColors = useMemo<Record<number, string>>(() => {
    const color =
      config.state.strategies[HOD_MOMO_RUNNING_UP_STRATEGY_ID]?.color || meta?.color || '#FF6E40';
    return { [HOD_MOMO_RUNNING_UP_STRATEGY_ID]: color };
  }, [config.state.strategies, meta?.color]);

  const visibleStrategies = useMemo(
    () => new Set([HOD_MOMO_RUNNING_UP_STRATEGY_ID]),
    [],
  );

  const strategyCounts = useMemo<Record<number, number>>(
    () => ({ [HOD_MOMO_RUNNING_UP_STRATEGY_ID]: alerts.length }),
    [alerts.length],
  );

  const visibleAlerts = useMemo(
    () => collapseAlertsBySymbol(alerts),
    [alerts],
  );

  return (
    <div className="hod-momo-tab running-up-tab">
      <div className="hod-header-bar">
        <div className="hod-header-left">
          <span className={`hod-connection-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span className="hod-header-title">Running Up Scanner</span>
          <span className="hod-alert-count">{totalToday ?? alerts.length} alerts today</span>
        </div>
        <div className="hod-header-right">
          <button
            type="button"
            className="hod-clear-btn"
            onClick={onClearAlerts}
            title="Clear today's Running Up alerts from the shared alert store"
          >
            Clear today
          </button>
          <button
            type="button"
            className="hod-settings-btn"
            onClick={onOpenSettings}
            title="Configure Running Up (strategy #12)"
          >
            ⚙ Configure
          </button>
        </div>
      </div>

      <p className="hod-scanner-blurb">
        Quick upward moves without requiring a new high of day (Warrior sibling of HOD Momentum).
      </p>

      <HodMomoAlertTable
        alerts={visibleAlerts}
        connected={connected}
        consolidationSec={consolidationSec}
        configColors={configColors}
        strategyCounts={strategyCounts}
        visibleStrategies={visibleStrategies}
        onToggleStrategy={() => {}}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={onSelectSymbol}
        onOpenTrading={onOpenTrading}
        showStrategyFilter={false}
        emptyWaiting="Waiting for Running Up alerts (surge / RVOL — no new HOD required)…"
        emptyConnecting="Connecting to Running Up feed…"
      />
    </div>
  );
}
