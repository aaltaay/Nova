/** Scanner empty / loading / disconnected messages for the main feed area. */
import { EMPTY_IBKR_DISCONNECTED, GAPPER_MIN_GAP_PCT } from '../constants';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import type { MarketMode } from './AppHeader';

interface HealthStatus {
  status: string;
  latency_ms: number;
  message?: string;
}

export function EmptyState({
  health,
  context,
  discoveryProvider,
}: {
  health: HealthStatus;
  context: MarketMode;
  /** When 'ibkr' and Gateway is down, show that instead of "no gaps yet". */
  discoveryProvider?: string;
}) {
  const ibkr = useIbkrStatus();

  if (context === 'loading') {
    return <div className="empty-state">Loading market data…</div>;
  }
  if (health.status === 'disconnected' || health.status === 'error') {
    return (
      <div className="empty-state">
        {health.message || 'Check API keys in Settings.'}
      </div>
    );
  }
  if (discoveryProvider === 'ibkr' && !ibkr.connected) {
    return <div className="empty-state empty-state--ibkr-down">{EMPTY_IBKR_DISCONNECTED}</div>;
  }
  if (context === 'closed') {
    return (
      <div className="empty-state">
        Market is closed — showing last available data. Scanning continues in the background.
      </div>
    );
  }
  if (context === 'premarket') {
    return (
      <div className="empty-state">
        No gappers with a gap of at least {GAPPER_MIN_GAP_PCT}% yet — scan running…
      </div>
    );
  }
  if (context === 'afterhours') {
    return (
      <div className="empty-state">
        No after-hours movers with a gap of at least {GAPPER_MIN_GAP_PCT}% yet — scan running…
      </div>
    );
  }
  return <div className="empty-state">No gainers in the feed right now.</div>;
}
