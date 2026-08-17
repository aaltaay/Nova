import {
  HEADER_GATEWAY_DELAYED_LABEL,
  HEADER_GATEWAY_OFFLINE_LABEL,
  HEADER_GATEWAY_UP_LABEL,
} from '../constants';
import type { IbkrMode } from '../ibkr/types';
import type { HealthStatus } from '../types/health';

export type HeaderChipTone = 'ok' | 'bad' | 'warn' | 'live';

export function resolveGatewayModeTag(
  ibkrMode: IbkrMode,
  ibkrGatewayMode: 'paper' | 'live' | null,
): 'paper' | 'live' | null {
  if (ibkrMode === 'paper' || ibkrMode === 'live') return ibkrMode;
  if (ibkrGatewayMode === 'paper' || ibkrGatewayMode === 'live') return ibkrGatewayMode;
  return null;
}

/** Gateway chip value: connection only. Mode is the Paper | Live capsule. */
export function gatewayConnectionLabel(args: {
  connected: boolean;
  delayed: boolean;
  launchBusy?: boolean;
  launchOk?: boolean | null;
}): string {
  if (args.launchBusy) return 'opening…';
  if (args.launchOk === true) return 'check desktop';
  if (args.launchOk === false) return 'launch failed';
  if (!args.connected) return HEADER_GATEWAY_OFFLINE_LABEL;
  if (args.delayed) return HEADER_GATEWAY_DELAYED_LABEL;
  return HEADER_GATEWAY_UP_LABEL;
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
