/**
 * Trading Prerequisites checklist -- single model for "can I trade?"
 * Required services: Nova API, IB Gateway (READY), spend armed.
 * Alpaca is never a prerequisite.
 */
import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_WEDGED,
} from '../constants';
import type { HealthStatus } from '../types/health';
import {
  PREREQ_GATEWAY_LOGIN_DETAIL,
  PREREQ_GATEWAY_PORT_OPEN_DETAIL,
} from './gatewayUxConstants';

export type PrereqId = 'nova_api' | 'ibkr_gateway' | 'ibkr_enabled' | 'orders_armed';

export type PrereqAction =
  | 'start_api'
  | 'launch_gateway'
  | 'reconnect_ibkr'
  | 'env_spend'
  | null;

export interface PrereqItem {
  id: PrereqId;
  ok: boolean;
  label: string;
  detail: string;
  action: PrereqAction;
}

export interface TradingPrerequisitesInput {
  health: HealthStatus | null | undefined;
  ibkrEnabled?: boolean;
  ibkrConnected: boolean;
  spendStatus?: string | null;
  /** Raw socket -- true while session may still be syncing / degraded. */
  ibkrTransportConnected?: boolean | null;
  /** Preferred Gateway API port accepts TCP (status.preferred_port_reachable). */
  preferredPortReachable?: boolean | null;
  /** status.disconnect_hint */
  disconnectHint?: string | null;
  /** status.session_reason */
  sessionReason?: string | null;
}

export interface TradingPrerequisites {
  items: PrereqItem[];
  /** True when Nova API + IBKR Gateway are up (desk may browse; trade still needs spend). */
  deskReady: boolean;
  /** True when deskReady and orders are paper_armed or live_armed. */
  tradeReady: boolean;
  /** Show blocking overlay -- desk not ready (API or Gateway down). */
  blockDesk: boolean;
}

function novaApiOk(health: HealthStatus | null | undefined): boolean {
  // Pending first probe: do not flash the gate before diagnose finishes.
  if (!health || health.status === 'loading') return true;
  if (health.flag === BACKEND_DIAG_FLAG_DOWN || health.flag === BACKEND_DIAG_FLAG_WEDGED) {
    return false;
  }
  return health.status === 'connected';
}

function novaApiDetail(health: HealthStatus | null | undefined): string {
  if (!health || health.status === 'loading') {
    return 'Checking Nova API on port 8000…';
  }
  if (health.flag === BACKEND_DIAG_FLAG_DOWN) {
    return health.flag_hint || health.message || 'Nothing answering on port 8000.';
  }
  if (health.flag === BACKEND_DIAG_FLAG_WEDGED) {
    return health.flag_hint || health.message || 'API process hung (health timed out).';
  }
  if (health.status === 'connected') {
    return 'Nova API process is reachable on port 8000.';
  }
  return health.message || health.flag_hint || `API status: ${health.status}`;
}

function spendArmed(spendStatus: string | null | undefined): boolean {
  return spendStatus === 'paper_armed' || spendStatus === 'live_armed';
}

function spendDetail(spendStatus: string | null | undefined): string {
  if (spendStatus === 'paper_armed') return 'Paper orders armed (IBKR_ORDERS_ENABLED).';
  if (spendStatus === 'live_armed') {
    return 'Live orders armed (IBKR_ORDERS_ENABLED + IBKR_LIVE_TRADING_CONFIRMED).';
  }
  if (spendStatus === 'locked_live_unconfirmed') {
    return 'Orders need IBKR_LIVE_TRADING_CONFIRMED=true in .env for live money.';
  }
  if (spendStatus === 'locked') {
    return 'Orders locked — set IBKR_ORDERS_ENABLED=true in .env (never auto-unlocked).';
  }
  return 'Spend status unknown — check Trading tab / .env.';
}

/** Gateway desktop is up (API port listening) but Nova usable-session is not. */
export function gatewayPortOpenButSessionDown(input: {
  preferredPortReachable?: boolean | null;
  disconnectHint?: string | null;
  ibkrTransportConnected?: boolean | null;
}): boolean {
  const hint = input.disconnectHint ?? null;
  if (
    hint === 'live_port_open_but_disconnected'
    || hint === 'paper_port_open_but_disconnected'
  ) {
    return true;
  }
  if (input.preferredPortReachable === true && input.ibkrTransportConnected !== true) {
    return true;
  }
  return false;
}

function gatewayDetail(input: TradingPrerequisitesInput, gatewayOk: boolean): string {
  if (gatewayOk) {
    return 'Gateway connected — live prices and order path available.';
  }
  if (gatewayPortOpenButSessionDown(input)) {
    const reason = (input.sessionReason || '').trim();
    if (reason && reason !== 'ok' && reason !== 'disconnected') {
      return `${PREREQ_GATEWAY_PORT_OPEN_DETAIL} (reason: ${reason})`;
    }
    return PREREQ_GATEWAY_PORT_OPEN_DETAIL;
  }
  return PREREQ_GATEWAY_LOGIN_DETAIL;
}

/** Pure builder — unit-test without React. */
export function buildTradingPrerequisites(
  input: TradingPrerequisitesInput,
): TradingPrerequisites {
  const apiOk = novaApiOk(input.health);
  const enabled = input.ibkrEnabled !== false;
  const gatewayOk = Boolean(input.ibkrConnected);
  const ordersOk = spendArmed(input.spendStatus);
  const portOpenStuck = !gatewayOk && gatewayPortOpenButSessionDown(input);

  const items: PrereqItem[] = [
    {
      id: 'nova_api',
      ok: apiOk,
      label: 'Nova API (:8000)',
      detail: novaApiDetail(input.health),
      action: apiOk ? null : 'start_api',
    },
    {
      id: 'ibkr_enabled',
      ok: enabled,
      label: 'IBKR enabled',
      detail: enabled
        ? 'IBKR_ENABLED is on.'
        : 'Set IBKR_ENABLED=true in .env and restart the API.',
      action: enabled ? null : 'env_spend',
    },
    {
      id: 'ibkr_gateway',
      ok: gatewayOk,
      label: 'IB Gateway (session READY)',
      detail: gatewayDetail(input, gatewayOk),
      action: gatewayOk ? null : portOpenStuck ? 'reconnect_ibkr' : 'launch_gateway',
    },
    {
      id: 'orders_armed',
      ok: ordersOk,
      label: 'Orders armed',
      detail: spendDetail(input.spendStatus),
      action: ordersOk ? null : 'env_spend',
    },
  ];

  const deskReady = apiOk && enabled && gatewayOk;
  const tradeReady = deskReady && ordersOk;

  return {
    items,
    deskReady,
    tradeReady,
    blockDesk: !deskReady,
  };
}
