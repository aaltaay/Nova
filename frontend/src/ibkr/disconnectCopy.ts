/**
 * Honest IBKR disconnect / port-mismatch copy for Stock View + empty states.
 */
import {
  EMPTY_IBKR_DISCONNECTED,
  EMPTY_IBKR_DISCONNECTED_LIVE,
  EMPTY_IBKR_DISCONNECTED_PAPER,
  STOCK_VIEW_DISCONNECTED_LABEL,
  STOCK_VIEW_DISCONNECT_HINT_BOTH_DOWN,
  STOCK_VIEW_DISCONNECT_HINT_LIVE_PAPER_UP,
  STOCK_VIEW_DISCONNECT_HINT_PAPER_LIVE_UP,
  STOCK_VIEW_DISCONNECT_HINT_PORT_OPEN,
} from '../constants';
import type { IbkrStatus } from './types';

export function emptyIbkrDisconnectedMessage(
  gatewayMode?: 'paper' | 'live' | null,
): string {
  if (gatewayMode === 'paper') return EMPTY_IBKR_DISCONNECTED_PAPER;
  if (gatewayMode === 'live') return EMPTY_IBKR_DISCONNECTED_LIVE;
  return EMPTY_IBKR_DISCONNECTED;
}

/** Human label for the Stock View disconnected warn / CTA. */
export function stockViewDisconnectLabel(status: Partial<IbkrStatus>): string {
  const hint = status.disconnect_hint;
  if (hint === 'paper_port_refused_live_listening') {
    return STOCK_VIEW_DISCONNECT_HINT_PAPER_LIVE_UP;
  }
  if (hint === 'live_port_refused_paper_listening') {
    return STOCK_VIEW_DISCONNECT_HINT_LIVE_PAPER_UP;
  }
  if (hint === 'both_ports_unreachable') {
    return STOCK_VIEW_DISCONNECT_HINT_BOTH_DOWN;
  }
  if (
    hint === 'paper_port_open_but_disconnected' ||
    hint === 'live_port_open_but_disconnected'
  ) {
    return STOCK_VIEW_DISCONNECT_HINT_PORT_OPEN;
  }
  return STOCK_VIEW_DISCONNECTED_LABEL;
}

/** Suggested switch target when a port-mismatch hint is present. */
export function disconnectHintSwitchTarget(
  hint: string | null | undefined,
): 'paper' | 'live' | null {
  if (hint === 'paper_port_refused_live_listening') return 'live';
  if (hint === 'live_port_refused_paper_listening') return 'paper';
  return null;
}
