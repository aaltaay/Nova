/** Scanner empty / loading / disconnected messages for the main feed area. */
import { GAPPER_MIN_GAP_PCT } from '../constants';
import type { MarketMode } from './AppHeader';

interface HealthStatus {
  status: string;
  latency_ms: number;
  message?: string;
}

export function EmptyState({
  health,
  context,
}: {
  health: HealthStatus;
  context: MarketMode;
}) {
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
