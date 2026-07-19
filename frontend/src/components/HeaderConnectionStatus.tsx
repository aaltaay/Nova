/**
 * Header connection cluster — API, market-data gateway/feed, and price freshness
 * as three labeled signals so "Connected" is never ambiguous.
 */
import { useCallback, useState } from 'react';
import { BackendStartButton } from './BackendStartButton';
import {
  DATA_FEED_LABELS,
  DISCOVERY_PROVIDER_DEFAULT,
  EMPTY_IBKR_DISCONNECTED,
  HEADER_GATEWAY_LAUNCH_HINT,
  SCANNER_DATA_SOURCE_TITLES,
} from '../constants';
import type { HealthStatus } from '../types/health';
import { formatScanAge } from '../utils/formatScanAge';
import { launchIbGateway } from '../utils/launchIbGateway';

type ChipTone = 'ok' | 'bad' | 'warn';

function apiTone(status: string): ChipTone {
  if (status === 'connected') return 'ok';
  if (status === 'disconnected' || status === 'error') return 'bad';
  return 'warn';
}

function apiLabel(status: string): string {
  if (status === 'connected') return 'up';
  if (status === 'disconnected') return 'down';
  if (status === 'error') return 'error';
  if (status === 'loading') return 'checking…';
  return status;
}

function toneDot(tone: ChipTone): string {
  if (tone === 'ok') return 'connected';
  if (tone === 'bad') return 'disconnected';
  return 'loading';
}

interface Props {
  health: HealthStatus;
  discoveryProvider?: string;
  ibkrConnected?: boolean;
  activeFeed: string;
  feedFellBack: boolean;
  secondsAgo: number | null;
  pricesStale?: boolean;
  historyDate: string | null;
  compact?: boolean;
  showScannerSource?: boolean;
  onBackendStarted?: () => void;
}

export function HeaderConnectionStatus({
  health,
  discoveryProvider = DISCOVERY_PROVIDER_DEFAULT,
  ibkrConnected = false,
  activeFeed,
  feedFellBack,
  secondsAgo,
  pricesStale = false,
  historyDate,
  compact = false,
  showScannerSource = true,
  onBackendStarted,
}: Props) {
  const [gatewayLaunchHint, setGatewayLaunchHint] = useState<string | null>(null);
  const [gatewayLaunchBusy, setGatewayLaunchBusy] = useState(false);
  const [gatewayLaunchOk, setGatewayLaunchOk] = useState<boolean | null>(null);

  const onGatewayDoubleClick = useCallback(async () => {
    if (gatewayLaunchBusy) return;
    setGatewayLaunchBusy(true);
    setGatewayLaunchOk(null);
    setGatewayLaunchHint('Opening IB Gateway…');
    const result = await launchIbGateway();
    setGatewayLaunchOk(result.ok);
    setGatewayLaunchHint(result.message);
    setGatewayLaunchBusy(false);
    window.setTimeout(() => {
      setGatewayLaunchHint(null);
      setGatewayLaunchOk(null);
    }, 10_000);
  }, [gatewayLaunchBusy]);

  const apiOk = health.status === 'connected';
  const apiChipTone = apiTone(health.status);
  const isIbkr = discoveryProvider === 'ibkr';
  const showPrices = !compact && !historyDate && secondsAgo != null;
  const priceTone: ChipTone = pricesStale ? 'warn' : 'ok';
  const priceText = showPrices
    ? pricesStale
      ? `stale · ${formatScanAge(secondsAgo)}`
      : formatScanAge(secondsAgo)
    : null;

  const gatewayTitle = [
    ibkrConnected ? SCANNER_DATA_SOURCE_TITLES.ibkr : EMPTY_IBKR_DISCONNECTED,
    HEADER_GATEWAY_LAUNCH_HINT,
    gatewayLaunchHint,
  ]
    .filter(Boolean)
    .join('\n\n');

  return (
    <div
      className="status-cluster"
      role="group"
      aria-label="Connection and data freshness"
    >
      <span
        className={`status-chip status-chip--${apiChipTone}`}
        title={
          apiOk
            ? 'Nova API process is reachable (local backend health check). This is not IB Gateway.'
            : health.flag_hint ||
              health.message ||
              'Nova API is unreachable — start the backend to restore scanner and quotes.'
        }
        data-testid="status-chip-api"
      >
        <span className={`dot ${toneDot(apiChipTone)}`} />
        <span className="status-chip__role">API</span>
        <span className="status-chip__value">
          {apiLabel(health.status)}
          {health.latency_ms > 0 ? ` · ${health.latency_ms}ms` : ''}
        </span>
      </span>

      {showScannerSource && isIbkr && (
        <>
          <button
            type="button"
            className={`status-chip status-chip--action status-chip--${
              gatewayLaunchOk === false
                ? 'bad'
                : gatewayLaunchOk === true
                  ? 'ok'
                  : ibkrConnected
                    ? 'ok'
                    : 'bad'
            }${gatewayLaunchBusy ? ' status-chip--busy' : ''}`}
            title={gatewayTitle}
            data-testid="status-chip-gateway"
            onDoubleClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              void onGatewayDoubleClick();
            }}
            aria-label="IB Gateway status. Double-click to open or focus Gateway."
          >
            <span
              className={`dot ${
                gatewayLaunchBusy
                  ? 'loading'
                  : ibkrConnected || gatewayLaunchOk === true
                    ? 'connected'
                    : 'disconnected'
              }`}
            />
            <span className="status-chip__role">Gateway</span>
            <span className="status-chip__value">
              {gatewayLaunchBusy
                ? 'opening…'
                : gatewayLaunchOk === true
                  ? 'check desktop'
                  : gatewayLaunchOk === false
                    ? 'launch failed'
                    : ibkrConnected
                      ? 'connected'
                      : 'offline'}
            </span>
          </button>
          {gatewayLaunchHint && (
            <span
              className={`status-hint status-hint--gateway${
                gatewayLaunchOk === false ? ' status-hint--error' : ''
              }`}
              data-testid="status-gateway-launch-hint"
              title={gatewayLaunchHint}
            >
              {gatewayLaunchHint.length > 72
                ? `${gatewayLaunchHint.slice(0, 72)}…`
                : gatewayLaunchHint}
            </span>
          )}
        </>
      )}

      {showScannerSource && !isIbkr && (
        <span
          className={`status-chip status-chip--${feedFellBack ? 'warn' : 'ok'}`}
          title={
            feedFellBack
              ? 'SIP feed was rejected; automatically fell back to IEX. Change in Settings if your plan supports SIP.'
              : SCANNER_DATA_SOURCE_TITLES.alpaca ||
                `Alpaca data feed: ${DATA_FEED_LABELS[activeFeed] || activeFeed.toUpperCase()}`
          }
          data-testid="status-chip-feed"
        >
          <span className={`dot ${feedFellBack ? 'loading' : 'connected'}`} />
          <span className="status-chip__role">Feed</span>
          <span className="status-chip__value">
            Alpaca {activeFeed.toUpperCase()}
            {feedFellBack ? ' · fallback' : ''}
          </span>
        </span>
      )}

      {priceText != null && (
        <span
          className={`status-chip status-chip--${priceTone}`}
          title={
            pricesStale
              ? 'Last successful table price tick is late or skipped — prices are not live right now.'
              : 'Age of the last successful table price tick for the active scanner tab.'
          }
          data-testid="status-chip-prices"
        >
          <span className={`dot ${pricesStale ? 'loading' : 'connected'}`} />
          <span className="status-chip__role">Prices</span>
          <span className="status-chip__value">{priceText}</span>
        </span>
      )}

      {health.flag && !apiOk && (
        <span
          className={`backend-flag backend-flag--${health.flag.toLowerCase()}`}
          title={health.flag_hint || health.message || health.flag}
          data-testid="backend-flag"
          data-flag={health.flag}
        >
          {health.flag}
        </span>
      )}
      {health.message && !apiOk && (
        <span className="status-hint" title={health.flag_hint || health.message}>
          {health.message.length > 80 ? `${health.message.slice(0, 80)}…` : health.message}
        </span>
      )}
      {!compact && (health.status === 'disconnected' || health.status === 'error') && (
        <BackendStartButton
          onStarted={onBackendStarted}
          flag={health.flag}
          flagHint={health.flag_hint}
        />
      )}
    </div>
  );
}
