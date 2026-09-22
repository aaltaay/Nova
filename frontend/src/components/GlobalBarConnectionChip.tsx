/**
 * One quiet connection chip right after the ET clock: `● IBKR live` (muted
 * green), `STALE 42s` / `SAMPLE DATA` (amber), `IBKR offline` / `API down`
 * (red). Click opens the same API + Gateway checklist the old Desk chip did;
 * double-click launches the Gateway target. The honesty text, feed-fallback
 * wording, price age and scanner mode live in its tooltip
 * (globalBarConnectionModel). While the API is down the Start API button
 * stays mounted beside it so its one-shot auto-heal still runs.
 */
import { useCallback, useState } from 'react';
import {
  DISCOVERY_PROVIDER_DEFAULT,
  GLOBAL_BAR_CONNECTION_API_DOWN_TITLE,
  GLOBAL_BAR_CONNECTION_API_UP_TITLE,
  GLOBAL_BAR_CONNECTION_ARIA,
  GLOBAL_BAR_CONNECTION_CLICK_HINT,
} from '../constants';
import type { IbkrMode } from '../ibkr/types';
import { openTradingPrerequisites } from '../ibkr/tradingPrereqUi';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import type { HealthStatus } from '../types/health';
import { launchIbGateway } from '../utils/launchIbGateway';
import { BackendStartButton } from './BackendStartButton';
import { SCANNER_MODE_LABELS, type GlobalAppBarScanner } from './globalAppBarScanner';
import { connectionChipView } from './globalBarConnectionModel';
import { apiProcessOk, deskGatewayView } from './headerConnectionStatusModel';

const LOADING_HEALTH: HealthStatus = { status: 'loading', latency_ms: 0 };
const LAUNCH_HINT_MS = 10_000;

interface Props {
  scanner: GlobalAppBarScanner | null;
  ibkrConnected: boolean;
  ibkrMode: IbkrMode;
  ibkrGatewayMode: 'paper' | 'live' | null;
  ibkrAccountKind: string | null;
}

function apiTitleFor(health: HealthStatus, apiOk: boolean): string {
  if (apiOk) return GLOBAL_BAR_CONNECTION_API_UP_TITLE;
  const why = health.flag_hint || health.message || GLOBAL_BAR_CONNECTION_API_DOWN_TITLE;
  return health.flag ? `${health.flag} -- ${why}` : why;
}

export function GlobalBarConnectionChip({
  scanner,
  ibkrConnected,
  ibkrMode,
  ibkrGatewayMode,
  ibkrAccountKind,
}: Props) {
  const live = useIbkrStatus();
  const [launchBusy, setLaunchBusy] = useState(false);
  const [launchOk, setLaunchOk] = useState<boolean | null>(null);
  const [launchHint, setLaunchHint] = useState<string | null>(null);

  const onDoubleClick = useCallback(async () => {
    if (launchBusy) return;
    setLaunchBusy(true);
    setLaunchOk(null);
    setLaunchHint('Opening IB Gateway…');
    const result = await launchIbGateway();
    setLaunchOk(result.ok);
    setLaunchHint(result.message);
    setLaunchBusy(false);
    window.setTimeout(() => {
      setLaunchHint(null);
      setLaunchOk(null);
    }, LAUNCH_HINT_MS);
  }, [launchBusy]);

  const health = scanner?.health ?? LOADING_HEALTH;
  const apiOk = apiProcessOk(health);
  const apiDown = health.status === 'disconnected' || health.status === 'error';
  const statusStale = live.stale === true;
  const staleForSec =
    statusStale && live.staleSince != null ? Math.floor((Date.now() - live.staleSince) / 1000) : null;
  const delayed = Boolean(live.market_data_delayed);
  const { title: gatewayTitle } = deskGatewayView({
    ibkrMode,
    gatewayMode: ibkrGatewayMode,
    accountKind: ibkrAccountKind ?? live.broker_account_kind ?? null,
    connected: ibkrConnected,
    delayed,
    statusStale,
    launchOk,
    launchHint,
    completedOrdersUnansweredSince: live.completed_orders_unanswered_since,
  });
  const provider = scanner?.discoveryProvider ?? DISCOVERY_PROVIDER_DEFAULT;
  const view = connectionChipView({
    sampleDataActive: Boolean(scanner?.sampleDataActive),
    apiOk,
    apiTitle: apiTitleFor(health, apiOk),
    connected: ibkrConnected,
    statusStale,
    staleForSec,
    delayed,
    gatewayTitle,
    pricesStale: Boolean(scanner?.pricesStale),
    secondsAgo: scanner?.secondsAgo ?? null,
    lastPriceTs: scanner?.lastPriceTs,
    historyDate: scanner?.historyDate ?? null,
    honestyText: scanner?.honestyText,
    isIbkr: provider === 'ibkr',
    activeFeed: scanner?.activeFeed ?? '',
    feedFellBack: Boolean(scanner?.feedFellBack),
    scannerModeLabel: scanner && !scanner.sampleDataActive ? SCANNER_MODE_LABELS[scanner.mode] : null,
  });

  return (
    <>
      <button
        type="button"
        className={`global-app-bar__conn global-app-bar__conn--${view.tone}${launchBusy ? ' is-busy' : ''}`}
        data-testid="global-bar-connection"
        data-state={view.state}
        title={view.title}
        aria-label={`${GLOBAL_BAR_CONNECTION_ARIA}: ${view.label}. ${GLOBAL_BAR_CONNECTION_CLICK_HINT}`}
        onClick={(e) => {
          e.preventDefault();
          openTradingPrerequisites();
        }}
        onDoubleClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          void onDoubleClick();
        }}
      >
        <span className="global-app-bar__conn-dot" aria-hidden="true" />
        <span className="global-app-bar__conn-label">{view.label}</span>
      </button>
      {launchHint && (
        <span
          className={`status-hint status-hint--gateway${launchOk === false ? ' status-hint--error' : ''}`}
          data-testid="status-gateway-launch-hint"
          title={launchHint}
        >
          {launchHint.length > 72 ? `${launchHint.slice(0, 72)}…` : launchHint}
        </span>
      )}
      {apiDown && !scanner?.sampleDataActive && (
        <BackendStartButton
          onStarted={scanner?.onBackendStarted}
          flag={health.flag}
          flagHint={health.flag_hint}
        />
      )}
    </>
  );
}
