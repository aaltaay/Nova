import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_UNREACHABLE,
  BACKEND_DIAG_FLAG_WEDGED,
  HEADER_GATEWAY_DELAYED_LABEL,
  HEADER_GATEWAY_LAUNCH_HINT,
  HEADER_GATEWAY_OFFLINE_LABEL,
  HEADER_GATEWAY_SIM_LABEL,
  HEADER_GATEWAY_STALE_LABEL,
  HEADER_GATEWAY_TITLE_DELAYED,
  HEADER_GATEWAY_TITLE_LIVE,
  HEADER_GATEWAY_TITLE_PAPER,
  HEADER_GATEWAY_TITLE_SIM,
  HEADER_GATEWAY_TITLE_UNKNOWN,
  HEADER_GATEWAY_UP_LABEL,
  SCANNER_DATA_SOURCE_TITLES,
} from '../constants';
import { emptyIbkrDisconnectedMessage } from '../ibkr/disconnectCopy';
import {
  HEADER_DESK_API_DOWN_LABEL,
  PREREQ_COMPLETED_ORDERS_STUCK_DETAIL,
} from '../ibkr/gatewayUxConstants';
import { completedOrdersStuckNotice } from '../ibkr/tradingPrerequisites';
import type { IbkrMode } from '../ibkr/types';
import type { HealthStatus } from '../types/health';

export type HeaderChipTone = 'ok' | 'bad' | 'warn' | 'live';

/**
 * Gateway half of the Desk chip: tooltip lines + tone. The D-058 notice
 * ("Completed orders not answering since …") is amber like delayed data and
 * uses the same helper as the Trading prerequisites panel.
 */
export function deskGatewayView(args: {
  ibkrMode: IbkrMode;
  gatewayMode: 'paper' | 'live' | null;
  accountKind: string | null;
  connected: boolean;
  delayed: boolean;
  statusStale: boolean;
  launchOk: boolean | null;
  launchHint: string | null;
  completedOrdersUnansweredSince?: number | null;
}): { tone: HeaderChipTone; title: string } {
  const sim = args.ibkrMode === 'sim';
  const modeTag = resolveGatewayModeTag(args.ibkrMode, args.gatewayMode, args.accountKind);
  const modeTitle = sim
    ? HEADER_GATEWAY_TITLE_SIM
    : modeTag === 'live'
      ? HEADER_GATEWAY_TITLE_LIVE
      : modeTag === 'paper'
        ? HEADER_GATEWAY_TITLE_PAPER
        : HEADER_GATEWAY_TITLE_UNKNOWN;
  const notice = completedOrdersStuckNotice({
    sinceEpochSec: args.completedOrdersUnansweredSince,
    gatewayReady: args.connected && !args.statusStale,
    simMode: sim,
  });
  const title = [
    modeTitle,
    args.connected
      ? SCANNER_DATA_SOURCE_TITLES.ibkr
      : emptyIbkrDisconnectedMessage(args.gatewayMode),
    args.delayed ? HEADER_GATEWAY_TITLE_DELAYED : null,
    notice ? `${notice}. ${PREREQ_COMPLETED_ORDERS_STUCK_DETAIL}` : null,
    HEADER_GATEWAY_LAUNCH_HINT,
    args.launchHint,
  ]
    .filter(Boolean)
    .join('\n\n');
  let tone: HeaderChipTone;
  if (sim) tone = 'warn';
  else if (args.launchOk === false) tone = 'bad';
  else if (args.launchOk === true) tone = 'ok';
  else if (args.statusStale) tone = 'warn';
  else if (!args.connected) tone = 'bad';
  else tone = args.delayed || notice ? 'warn' : 'ok';
  return { tone, title };
}

export function resolveGatewayModeTag(
  ibkrMode: IbkrMode,
  ibkrGatewayMode: 'paper' | 'live' | null,
  accountKind?: string | null,
): 'paper' | 'live' | null {
  if (ibkrMode === 'sim') return null;
  if (accountKind === 'paper' || accountKind === 'live') return accountKind;
  if (ibkrMode === 'paper' || ibkrMode === 'live') return ibkrMode;
  if (ibkrGatewayMode === 'paper' || ibkrGatewayMode === 'live') return ibkrGatewayMode;
  return null;
}

/** Gateway chip value: connection only. Mode is the Paper | Live capsule. */
export function gatewayConnectionLabel(args: {
  connected: boolean;
  delayed: boolean;
  stale?: boolean;
  launchBusy?: boolean;
  launchOk?: boolean | null;
}): string {
  if (args.launchBusy) return 'opening…';
  if (args.launchOk === true) return 'check desktop';
  if (args.launchOk === false) return 'launch failed';
  if (args.stale) return HEADER_GATEWAY_STALE_LABEL;
  if (!args.connected) return HEADER_GATEWAY_OFFLINE_LABEL;
  if (args.delayed) return HEADER_GATEWAY_DELAYED_LABEL;
  return HEADER_GATEWAY_UP_LABEL;
}

/** Nova process on :8000 -- not IB Gateway, not Alpaca. */
export function apiProcessOk(health: HealthStatus): boolean {
  if (!health || health.status === 'loading') return true;
  if (health.ib_loop_lag_ms?.wedged) return false;
  if (health.flag === BACKEND_DIAG_FLAG_WEDGED) return true;
  if (health.flag === BACKEND_DIAG_FLAG_UNREACHABLE) return true;
  if (health.flag === BACKEND_DIAG_FLAG_DOWN) return false;
  return health.status === 'connected';
}

/** One Desk chip: API-down wins, then Gateway offline / delayed / up. */
export function deskConnectionLabel(args: {
  apiOk: boolean;
  connected: boolean;
  delayed: boolean;
  stale?: boolean;
  launchBusy?: boolean;
  launchOk?: boolean | null;
  sim?: boolean;
}): string {
  if (!args.apiOk) return HEADER_DESK_API_DOWN_LABEL;
  if (args.sim) return HEADER_GATEWAY_SIM_LABEL;
  return gatewayConnectionLabel(args);
}

export function deskChipTone(args: {
  apiOk: boolean;
  gatewayTone: HeaderChipTone;
}): HeaderChipTone {
  if (!args.apiOk) return 'bad';
  return args.gatewayTone;
}

export function apiTone(status: string): HeaderChipTone {
  if (status === 'connected') return 'ok';
  if (status === 'disconnected' || status === 'error') return 'bad';
  return 'warn';
}

export function integrationTone(status: string): HeaderChipTone {
  if (status === 'ok') return 'ok';
  if (status === 'error') return 'bad';
  return 'warn';
}

export function apiLabel(status: string): string {
  if (status === 'connected') return 'up';
  if (status === 'disconnected') return 'down';
  if (status === 'error') return 'error';
  if (status === 'loading') return 'checking…';
  return status;
}

export function toneDot(tone: HeaderChipTone): string {
  if (tone === 'ok') return 'connected';
  if (tone === 'bad') return 'disconnected';
  return 'loading';
}

/** API chip no longer shows broker RTT -- Alpaca must not appear as "the API". */
export function healthLatencyLabel(_health: HealthStatus): string | null {
  return null;
}
