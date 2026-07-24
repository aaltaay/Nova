import {
  HEADER_GATEWAY_MODE_LIVE,
  HEADER_GATEWAY_MODE_PAPER,
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

export function gatewayModeLabel(tag: 'paper' | 'live' | null): string | null {
  if (tag === 'live') return HEADER_GATEWAY_MODE_LIVE;
  if (tag === 'paper') return HEADER_GATEWAY_MODE_PAPER;
  return null;
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

export function healthLatencyLabel(health: HealthStatus): string | null {
  if (health.latency_ms <= 0) return null;
  if (health.latency_source === 'alpaca_account_http') {
    return `Alpaca account RTT ${health.latency_ms}ms`;
  }
  return null;
}
