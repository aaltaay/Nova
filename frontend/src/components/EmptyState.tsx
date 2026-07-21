/** Scanner empty / loading / disconnected messages for the main feed area. */
import { GAPPER_MIN_GAP_PCT } from '../constants';
import { emptyIbkrDisconnectedMessage } from '../ibkr/disconnectCopy';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import type { MarketMode } from './AppHeader';
import type { HealthStatus } from '../types/health';

export function EmptyState({
  health,
  context,
  discoveryProvider,
  emptyLabel = 'gainers',
}: {
  health: HealthStatus;
  context: MarketMode;
  /** When 'ibkr' and Gateway is down, show that instead of "no gaps yet". */
  discoveryProvider?: string;
  /** Which feed's default "no X in the feed" message to show (Gainers/Losers sub-tabs). */
  emptyLabel?: 'gainers' | 'losers';
}) {
  const ibkr = useIbkrStatus();

  if (context === 'loading') {
    return <div className="empty-state">Loading market data…</div>;
  }
  if (health.status === 'disconnected' || health.status === 'error') {
    return (
      <div className="empty-state">
        {health.flag ? `${health.flag}: ` : ''}
        {health.message || 'Check API keys in Settings.'}
        {health.flag_hint ? (
          <div className="empty-state-hint">{health.flag_hint}</div>
        ) : null}
      </div>
    );
  }
  if (discoveryProvider === 'ibkr' && !ibkr.connected) {
    return (
      <div className="empty-state empty-state--ibkr-down">
        {emptyIbkrDisconnectedMessage(ibkr.gateway_mode)}
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
        No gappers with a gap of at least {GAPPER_MIN_GAP_PCT}% in the cache.
        <div className="empty-state-hint">
          If this stays empty while IBKR is connected, check the integrity banner above
          (bridge timeouts used to wipe the table silently). Open the <strong>Gainers</strong> tab
          — that feed may still be live.
        </div>
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
  return <div className="empty-state">No {emptyLabel} in the feed right now.</div>;
}
