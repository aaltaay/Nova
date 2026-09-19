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
  HEADER_GATEWAY_TITLE_SIM,
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
import { StockViewMarketClock } from '../stock_view/StockViewMarketClock';
import {
  HEADER_DESK_ROLE,
  PREREQ_COMPLETED_ORDERS_STUCK_DETAIL,
} from '../ibkr/gatewayUxConstants';
import { completedOrdersStuckNotice } from '../ibkr/tradingPrerequisites';
import { openTradingPrerequisites } from '../ibkr/tradingPrereqUi';
import {
  SCANNER_HONESTY_CHIP_ROLE,
  priceAgeChipText,
  showPriceAgeChip,
} from '../scanner/scannerHonesty';
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
  lastPriceTs?: number | null;
  pricesStale?: boolean;
  honestyText?: string | null;
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
  lastPriceTs,
  pricesStale = false,
  honestyText = null,
  historyDate,
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
  const showPrices = showPriceAgeChip({ historyDate, lastPriceTs, secondsAgo });
  const priceText = showPrices
    ? priceAgeChipText({
        lastPriceTs,
        secondsAgo,
        pricesStale,
        formatAge: formatScanAge,
      })
    : null;
  const priceTone: HeaderChipTone =
    lastPriceTs === 0 || pricesStale ? 'warn' : 'ok';

  const modeTag = resolveGatewayModeTag(ibkrMode, ibkrGatewayMode, ibkrAccountKind);
  const modeTitle =
    ibkrMode === 'sim'
      ? HEADER_GATEWAY_TITLE_SIM
      : modeTag === 'live'
        ? HEADER_GATEWAY_TITLE_LIVE
        : modeTag === 'paper'
          ? HEADER_GATEWAY_TITLE_PAPER
          : HEADER_GATEWAY_TITLE_UNKNOWN;
  // D-058: READY desk whose Gateway stopped answering completed orders.
  const completedOrdersNotice = completedOrdersStuckNotice({
    sinceEpochSec: ibkrStatusLive.completed_orders_unanswered_since,
    gatewayReady: ibkrConnected && ibkrStatusLive.stale !== true,
    simMode: ibkrMode === 'sim',
  });
  const gatewayTitle = [
    modeTitle,
    ibkrConnected
      ? SCANNER_DATA_SOURCE_TITLES.ibkr
      : emptyIbkrDisconnectedMessage(ibkrGatewayMode),
    marketDataDelayed ? HEADER_GATEWAY_TITLE_DELAYED : null,
    completedOrdersNotice
      ? `${completedOrdersNotice}. ${PREREQ_COMPLETED_ORDERS_STUCK_DETAIL}`
      : null,
    HEADER_GATEWAY_LAUNCH_HINT,
    gatewayLaunchHint,
  ]
    .filter(Boolean)
    .join('\n\n');

  const statusStale = ibkrStatusLive.stale === true;
  const gatewayChipTone: HeaderChipTone = ibkrMode === 'sim'
    ? 'warn'
    : gatewayLaunchOk === false
    ? 'bad'
    : gatewayLaunchOk === true
      ? 'ok'
      : statusStale
        ? 'warn'
        : !ibkrConnected
          ? 'bad'
          : marketDataDelayed || completedOrdersNotice
            ? 'warn'
            : 'ok';

  const deskValue = deskConnectionLabel({
    apiOk,
    connected: ibkrConnected,
    delayed: marketDataDelayed,
    stale: statusStale,
    launchBusy: gatewayLaunchBusy,
    launchOk: gatewayLaunchOk,
    sim: ibkrMode === 'sim',
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
          <StockViewMarketClock />
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

      {honestyText ? (
        <span
          className="status-chip status-chip--warn"
          title={honestyText}
          data-testid="status-chip-honesty"
        >
          <span className="dot loading" />
          <span className="status-chip__role">{SCANNER_HONESTY_CHIP_ROLE}</span>
          <span className="status-chip__value">{honestyText}</span>
        </span>
      ) : null}

      {priceText != null && (
        <span
          className={`status-chip status-chip--${priceTone}`}
          title={
            lastPriceTs === 0
              ? 'No IBKR L1 price_patch has arrived for the active scanner tab.'
              : pricesStale
                ? 'Last successful table price tick is late or skipped -- prices are not live right now.'
                : 'Age of the last successful table price tick for the active scanner tab.'
          }
          data-testid="status-chip-prices"
        >
          <span className={`dot ${lastPriceTs === 0 || pricesStale ? 'loading' : 'connected'}`} />
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
