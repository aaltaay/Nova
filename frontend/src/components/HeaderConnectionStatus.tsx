/**
 * Header connection cluster -- Desk (API + Gateway), Paper/Live, and freshness.
 * One Desk chip opens the same checklist; do not show API and Gateway as twins.
 */
import { useCallback, useState } from 'react';
import { BackendStartButton } from './BackendStartButton';
import { BackendReloadButton } from './BackendReloadButton';
import {
  DATA_FEED_LABELS,
  DISCOVERY_PROVIDER_DEFAULT,
  HEADER_GATEWAY_LAUNCH_HINT,
  HEADER_GATEWAY_TITLE_DELAYED,
  HEADER_GATEWAY_TITLE_LIVE,
  HEADER_GATEWAY_TITLE_PAPER,
  HEADER_GATEWAY_TITLE_UNKNOWN,
  HEADER_INTEGRATION_CHIP_LABELS,
  HEADER_INTEGRATION_CHIP_ORDER,
  SCANNER_DATA_SOURCE_TITLES,
} from '../constants';
import { emptyIbkrDisconnectedMessage } from '../ibkr/disconnectCopy';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import type { IbkrMode } from '../ibkr/types';
import type { HealthStatus, IntegrationChipStatus } from '../types/health';
import {
  formatScanAge,
} from '../utils/formatScanAge';
import { canReloadLocalBackend } from '../utils/startLocalApi';
import { launchIbGateway } from '../utils/launchIbGateway';
import { GatewayModeCapsule } from '../ibkr/GatewayModeCapsule';
import { HEADER_DESK_ROLE } from '../ibkr/gatewayUxConstants';
import { openTradingPrerequisites } from '../ibkr/tradingPrereqUi';
import {
  apiLabel,
  apiProcessOk,
  apiTone,
  deskChipTone,
  deskConnectionLabel,
  healthLatencyLabel,
  integrationTone,
  resolveGatewayModeTag,
  toneDot,
  type HeaderChipTone,
} from './headerConnectionStatusModel';

interface Props {
  health: HealthStatus;
  discoveryProvider?: string;
  ibkrConnected?: boolean;
  /** Live session mode from /api/ibkr/status (paper | live | disconnected). */
  ibkrMode?: IbkrMode;
  /** Configured Gateway port target when session mode is not yet known. */
  ibkrGatewayMode?: 'paper' | 'live' | null;
  ibkrAccountKind?: string | null;
  ibkrIntentionalMode?: 'paper' | 'live' | null;
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
  ibkrMode = 'disconnected',
  ibkrGatewayMode = null,
  ibkrAccountKind = null,
  ibkrIntentionalMode = null,
  activeFeed,
  feedFellBack,
  secondsAgo,
  pricesStale = false,
  historyDate,
  compact = false,
  showScannerSource = true,
  onBackendStarted,
}: Props) {
  const ibkrStatusLive = useIbkrStatus();
  const marketDataDelayed = Boolean(ibkrStatusLive.market_data_delayed);
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

  const apiOk = apiProcessOk(health);
  const apiChipTone = apiTone(health.status);
  const latencyLabel = healthLatencyLabel(health);
  const isIbkr = discoveryProvider === 'ibkr';
  const showPrices = !compact && !historyDate && secondsAgo != null;
  const priceTone: HeaderChipTone = pricesStale ? 'warn' : 'ok';
  const priceText = showPrices
    ? pricesStale
      ? `stale · ${formatScanAge(secondsAgo)}`
      : formatScanAge(secondsAgo)
    : null;

  const modeTag = resolveGatewayModeTag(ibkrMode, ibkrGatewayMode, ibkrAccountKind);
  const modeTitle =
    modeTag === 'live'
      ? HEADER_GATEWAY_TITLE_LIVE
      : modeTag === 'paper'
        ? HEADER_GATEWAY_TITLE_PAPER
        : HEADER_GATEWAY_TITLE_UNKNOWN;
  const gatewayTitle = [
    modeTitle,
    ibkrConnected
      ? SCANNER_DATA_SOURCE_TITLES.ibkr
      : emptyIbkrDisconnectedMessage(ibkrGatewayMode),
    marketDataDelayed ? HEADER_GATEWAY_TITLE_DELAYED : null,
    HEADER_GATEWAY_LAUNCH_HINT,
    gatewayLaunchHint,
  ]
    .filter(Boolean)
    .join('\n\n');

  const gatewayChipTone: HeaderChipTone = gatewayLaunchOk === false
    ? 'bad'
    : gatewayLaunchOk === true
      ? 'ok'
      : !ibkrConnected
        ? 'bad'
        : marketDataDelayed
          ? 'warn'
          : 'ok';

  const deskValue = deskConnectionLabel({
    apiOk,
    connected: ibkrConnected,
    delayed: marketDataDelayed,
    launchBusy: gatewayLaunchBusy,
    launchOk: gatewayLaunchOk,
  });
  const deskTone = deskChipTone({ apiOk, gatewayTone: gatewayChipTone });
  const deskTitle = [
    apiOk
      ? 'Nova API process is reachable on port 8000.'
      : health.flag_hint ||
        health.message ||
        'Nova API is unreachable -- start the backend (port 8000).',
    gatewayTitle,
  ].join('\n\n');

  return (
    <div
      className="status-cluster"
      role="group"
      aria-label="Connection and data freshness"
    >
      {showScannerSource && isIbkr && (
        <>
          <button
            type="button"
            className={`status-chip status-chip--action status-chip--${deskTone}${
              gatewayLaunchBusy ? ' status-chip--busy' : ''
            }`}
            title={deskTitle}
            data-testid="status-chip-desk"
            onClick={(e) => {
              e.preventDefault();
              openTradingPrerequisites();
            }}
            onDoubleClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              void onGatewayDoubleClick();
            }}
            aria-label={`Desk ${deskValue}. Click for API and Gateway checklist. X closes it. Double-click launches the current Gateway target.`}
          >
            <span
              className={`dot ${
                gatewayLaunchBusy
                  ? 'loading'
                  : toneDot(deskTone)
              }`}
            />
            <span className="status-chip__role">{HEADER_DESK_ROLE}</span>
            <span className="status-chip__value">
              {deskValue}
              {latencyLabel ? ` · ${latencyLabel}` : ''}
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
          <GatewayModeCapsule
            mode={ibkrMode}
            gatewayMode={ibkrGatewayMode ?? undefined}
            accountKind={ibkrAccountKind ?? ibkrStatusLive.broker_account_kind ?? null}
            intentionalMode={
              ibkrIntentionalMode ?? ibkrStatusLive.intentional_gateway_mode ?? null
            }
            disconnectHint={ibkrStatusLive.disconnect_hint}
            testId="header-gateway-mode-capsule"
          />
        </>
      )}

      {(!showScannerSource || !isIbkr) && (
        <span
          className={`status-chip status-chip--${apiChipTone}`}
          title={
            apiOk
              ? 'Nova API process is reachable on port 8000. Alpaca is not the API.'
              : health.flag_hint ||
                health.message ||
                'Nova API is unreachable -- start the backend (port 8000) to restore scanner and quotes.'
          }
          data-testid="status-chip-api"
        >
          <span className={`dot ${toneDot(apiChipTone)}`} />
          <span className="status-chip__role">API</span>
          <span className="status-chip__value">
            {apiLabel(health.status)}
            {latencyLabel ? ` · ${latencyLabel}` : ''}
          </span>
        </span>
      )}

      {showScannerSource && !isIbkr && (
        <span
          className={`status-chip status-chip--${feedFellBack ? 'warn' : 'ok'}`}
          title={
            feedFellBack
              ? 'SIP feed was rejected; automatically fell back to IEX. Change in Settings if your plan supports SIP.'
              : `Legacy Alpaca data feed: ${DATA_FEED_LABELS[activeFeed] || activeFeed.toUpperCase()} (not a product scanner source)`
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

      {HEADER_INTEGRATION_CHIP_ORDER.map((key) => {
        const chip: IntegrationChipStatus | undefined = health.integrations?.[key];
        if (!chip) return null;
        const tone = integrationTone(chip.status);
        const role = HEADER_INTEGRATION_CHIP_LABELS[key] || key;
        return (
          <span
            key={key}
            className={`status-chip status-chip--${tone}`}
            title={chip.detail || `${role} integration status`}
            data-testid={`status-chip-integration-${key}`}
          >
            <span className={`dot ${toneDot(tone)}`} />
            <span className="status-chip__role">{role}</span>
            <span className="status-chip__value">{chip.status}</span>
          </span>
        );
      })}

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
      {/* Always show in GlobalAppBar (compact): reload picks up backend code /
          resets cached_health; Start API recovers API_DOWN only (not WEDGED). */}
      {apiOk && canReloadLocalBackend() && (
        <BackendReloadButton onReloaded={onBackendStarted} />
      )}
      {(health.status === 'disconnected' || health.status === 'error') && (
        <BackendStartButton
          onStarted={onBackendStarted}
          flag={health.flag}
          flagHint={health.flag_hint}
        />
      )}
    </div>
  );
}
