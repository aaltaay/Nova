/** Scanner empty / loading / disconnected messages for the main feed area. */
import { GAPPER_MIN_GAP_PCT } from '../constants';
import { emptyIbkrDisconnectedMessage } from '../ibkr/disconnectCopy';
import { EMPTY_IBKR_RECONNECT_WARMUP } from '../ibkr/gatewayUxConstants';
import { useIbkrReconnectWarmup } from '../ibkr/useIbkrReconnectWarmup';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import type { MarketMode } from './AppHeader';
import type { HealthStatus } from '../types/health';

export function EmptyState({
  health,
  context,
  discoveryProvider,
  emptyLabel = 'gainers',
  historyDate = null,
  historyError = null,
  honestyHint = null,
}: {
  health: HealthStatus;
  context: MarketMode;
  /** When 'ibkr' and Gateway is down, show that instead of "no gaps yet". */
  discoveryProvider?: string;
  /** Which feed's default "no X in the feed" message to show (Gainers/Losers sub-tabs). */
  emptyLabel?: 'gappers' | 'gainers' | 'losers' | 'large cap movers' | 'after-hours movers';
  /** Past-date snapshot view -- do not reuse live market-closed copy. */
  historyDate?: string | null;
  historyError?: string | null;
  /** feed_error / unavailable -- do not sell this as a quiet market. */
  honestyHint?: string | null;
}) {
  const ibkr = useIbkrStatus();
  const isIbkr = discoveryProvider === 'ibkr';
  const warmingUp = useIbkrReconnectWarmup(isIbkr && ibkr.connected);

  if (context === 'loading') {
    return <div className="empty-state">Loading market data…</div>;
  }
  if (historyDate) {
    if (historyError) {
      return (
        <div className="empty-state">
          {historyError}
          <div className="empty-state-hint">
            This is a load failure, not an empty session. Click Back to Live for
            today&apos;s lists.
          </div>
        </div>
      );
    }
    return (
      <div className="empty-state">
        No saved {emptyLabel} for {historyDate}.
        <div className="empty-state-hint">
          This day&apos;s snapshot was empty when it was last written. Click
          Back to Live for today&apos;s lists.
        </div>
      </div>
    );
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
  if (isIbkr && !ibkr.connected) {
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
  if (honestyHint) {
    return (
      <div className="empty-state">
        {emptyLabel} feed: {honestyHint}
        <div className="empty-state-hint">
          This is not a quiet market. The roster did not commit a live list.
        </div>
      </div>
    );
  }
  if (context === 'premarket') {
    return (
      <div className="empty-state">
        No gainer is up at least {GAPPER_MIN_GAP_PCT}% yet.
        <div className="empty-state-hint">
          Premarket gappers are the <strong>Gainers</strong> roster filtered to a{' '}
          {GAPPER_MIN_GAP_PCT}% move, so this list fills as quotes arrive. If the
          Gainers tab is also empty while IBKR is connected, check the Roster /
          Prices chips -- that is a feed problem, not a quiet tape.
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
  // Only Gainers/Losers panels reach here with context 'market' (Gappers maps
  // 'market' -> 'premarket' copy above; Afterhours maps it -> 'afterhours' copy
  // above) — so this is exactly the fallthrough that used to read "no data"
  // right after a reconnect, before the roster/L1 stream finishes resubscribing.
  if (context === 'market' && isIbkr && ibkr.connected && warmingUp) {
    return (
      <div className="empty-state empty-state--ibkr-warmup">
        {EMPTY_IBKR_RECONNECT_WARMUP}
      </div>
    );
  }
  return <div className="empty-state">No {emptyLabel} in the feed right now.</div>;
}
