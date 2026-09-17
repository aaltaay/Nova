import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_UNREACHABLE,
  BACKEND_DIAG_FLAG_WEDGED,
  HEADER_GATEWAY_DELAYED_LABEL,
  HEADER_GATEWAY_OFFLINE_LABEL,
  HEADER_GATEWAY_STALE_LABEL,
  HEADER_GATEWAY_UP_LABEL,
} from '../constants';
import { HEADER_DESK_API_DOWN_LABEL } from '../ibkr/gatewayUxConstants';
import type { IbkrMode } from '../ibkr/types';
import type { HealthStatus } from '../types/health';

export type HeaderChipTone = 'ok' | 'bad' | 'warn' | 'live';

export function resolveGatewayModeTag(
  ibkrMode: IbkrMode,
  ibkrGatewayMode: 'paper' | 'live' | null,
  accountKind?: string | null,
): 'paper' | 'live' | null {
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
}): string {
  if (!args.apiOk) return HEADER_DESK_API_DOWN_LABEL;
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
