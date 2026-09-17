/**
 * Trading Prerequisites checklist -- desk connectivity only.
 * Required: Nova API, IBKR enabled, IB Gateway READY.
 * Order spend / PIN / ticket unlock stay on the trade path -- not this list.
 * Alpaca is never a prerequisite.
 */
import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_UNREACHABLE,
  BACKEND_DIAG_FLAG_WEDGED,
  DESK_API_FAIL_STREAK_FOR_OVERLAY,
} from '../constants';
import type { HealthStatus } from '../types/health';
import {
  PREREQ_GATEWAY_CLIENT_ID_DETAIL,
  PREREQ_GATEWAY_FOLLOW_LIVE_DETAIL,
  PREREQ_GATEWAY_FOLLOW_PAPER_DETAIL,
  PREREQ_GATEWAY_LOGIN_DETAIL,
  PREREQ_GATEWAY_PORT_OPEN_DETAIL,
  PREREQ_GATEWAY_STALE_SECOND_FACTOR_DETAIL,
} from './gatewayUxConstants';

export type PrereqId = 'nova_api' | 'ibkr_gateway' | 'ibkr_enabled';

export type PrereqAction =
  | 'start_api'
  | 'launch_gateway'
  | 'reconnect_ibkr'
  | 'switch_gateway_mode'
  | 'stale_second_factor'
  | 'env_ibkr'
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
  /** Raw socket -- true while session may still be syncing / degraded. */
  ibkrTransportConnected?: boolean | null;
  /** Preferred Gateway API port accepts TCP (status.preferred_port_reachable). */
  preferredPortReachable?: boolean | null;
  /** status.disconnect_hint */
  disconnectHint?: string | null;
  /** status.session_reason */
  sessionReason?: string | null;
  /** status.session_state (disconnected/connecting/synchronizing/ready/degraded) */
  sessionState?: string | null;
  /** status.second_factor_stale -- the on-screen prompt is already too old
   * for IBKR to honor, even if approved right now. */
  secondFactorStale?: boolean | null;
  /** status.second_factor_age_sec -- surfaced in the CTA detail copy. */
  secondFactorAgeSec?: number | null;
  /** Consecutive failed Nova API probes. One miss is not enough to overlay. */
  apiFailStreak?: number;
  /** Place / Flatten / Fill now in flight -- never steal the ticket. */
  deskActionInFlight?: boolean;
}

export interface TradingPrerequisites {
  items: PrereqItem[];
  /** True when Nova API + IBKR enabled + Gateway READY. */
  deskReady: boolean;
  /** Same as deskReady -- spend / ticket locks are outside this checklist. */
  tradeReady: boolean;
  /** Desk not ready (API or Gateway down). Does not by itself cover the UI. */
  blockDesk: boolean;
  /** Auto-cover the desk only when Nova API is actually down (not Gateway-only). */
  autoOverlay: boolean;
}

export function novaApiOk(health: HealthStatus | null | undefined): boolean {
  // Pending first probe: do not flash the gate before diagnose finishes.
  if (!health || health.status === 'loading') return true;
  if (health.ib_loop_lag_ms?.wedged) return false;
  // Client API_WEDGED is a probe timeout while the PID still listens (Trader
  // open / IB work). Do not cover the desk or offer Start API -- ADR 010.
  if (health.flag === BACKEND_DIAG_FLAG_WEDGED) return true;
  // Health probe succeeded; a different route timed out (#238).
  if (health.flag === BACKEND_DIAG_FLAG_UNREACHABLE) return true;
  if (health.flag === BACKEND_DIAG_FLAG_DOWN) return false;
  return health.status === 'connected';
}

function novaApiDetail(health: HealthStatus | null | undefined): string {
  if (!health || health.status === 'loading') {
    return 'Checking Nova API on port 8000…';
  }
  if (health.flag === BACKEND_DIAG_FLAG_DOWN) {
    return health.flag_hint || health.message || 'Nothing answering on port 8000.';
  }
  if (health.ib_loop_lag_ms?.wedged) {
    return 'IB loop wedged -- desk blocked. Do not restart the API from this banner.';
  }
  if (health.flag === BACKEND_DIAG_FLAG_WEDGED) {
    return health.flag_hint || health.message || 'IB loop or health probe stalled -- do not auto-kill the API.';
  }
  if (health.status === 'connected') {
    return 'Nova API process is reachable on port 8000.';
  }
  return health.message || health.flag_hint || `API status: ${health.status}`;
}

export function gatewayPortMismatchHint(
  hint: string | null | undefined,
): 'paper' | 'live' | null {
  if (hint === 'live_port_refused_paper_listening') return 'paper';
  if (hint === 'paper_port_refused_live_listening') return 'live';
  return null;
}

/**
 * Gateway desktop is up (API port listening) but Nova usable-session is not.
 * Only called when the caller already knows !connected, so the port alone
 * decides this -- whether the socket is down (ibkrTransportConnected=false)
 * OR up but the session never reached READY (ibkrTransportConnected=true,
 * e.g. the dialer froze after connect -- see PROBLEM_LOG 2026-08-31, where
 * this predicate's old `!== true` transport gate hid a 7-hour freeze behind
 * a "log into Gateway" prompt while the socket was healthy the whole time).
 */
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
  return input.preferredPortReachable === true;
}

function gatewayDetail(input: TradingPrerequisitesInput, gatewayOk: boolean): string {
  if (gatewayOk) {
    return 'Gateway connected -- live prices and order path available.';
  }
  if (input.secondFactorStale) {
    const age = Math.round(input.secondFactorAgeSec ?? 0);
    return `${PREREQ_GATEWAY_STALE_SECOND_FACTOR_DETAIL} (open ${age}s -- IBKR's own limit is 180s.)`;
  }
  const follow = gatewayPortMismatchHint(input.disconnectHint);
  if (follow === 'paper') return PREREQ_GATEWAY_FOLLOW_PAPER_DETAIL;
  if (follow === 'live') return PREREQ_GATEWAY_FOLLOW_LIVE_DETAIL;
  if (gatewayPortOpenButSessionDown(input)) {
    const reason = (input.sessionReason || '').trim();
    if (reason === 'client_id_in_use') {
      return PREREQ_GATEWAY_CLIENT_ID_DETAIL;
    }
    const state = (input.sessionState || '').trim();
    if (reason && reason !== 'ok' && reason !== 'disconnected') {
      const stateNote = state ? `, state: ${state}` : '';
      return `${PREREQ_GATEWAY_PORT_OPEN_DETAIL} (reason: ${reason}${stateNote})`;
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
  const followTarget = gatewayPortMismatchHint(input.disconnectHint);
  const portOpenStuck = !gatewayOk && gatewayPortOpenButSessionDown(input);
  const apiDown = input.health?.flag === BACKEND_DIAG_FLAG_DOWN;
  const apiWedged = input.health?.flag === BACKEND_DIAG_FLAG_WEDGED;
  let gatewayAction: PrereqAction = null;
  if (!gatewayOk) {
    if (input.secondFactorStale) gatewayAction = 'stale_second_factor';
    else if (followTarget) gatewayAction = 'switch_gateway_mode';
    else if (portOpenStuck || apiWedged) gatewayAction = 'reconnect_ibkr';
    else if (!apiDown) gatewayAction = 'launch_gateway';
  }

  const items: PrereqItem[] = [
    {
      id: 'nova_api',
      ok: apiOk,
      label: 'Nova API (:8000)',
      detail: novaApiDetail(input.health),
      action:
        !apiOk && input.health?.flag === BACKEND_DIAG_FLAG_DOWN ? 'start_api' : null,
    },
    {
      id: 'ibkr_enabled',
      ok: enabled,
      label: 'IBKR enabled',
      detail: enabled
        ? 'IBKR_ENABLED is on.'
        : 'Set IBKR_ENABLED=true in .env and restart the API.',
      action: enabled ? null : 'env_ibkr',
    },
    {
      id: 'ibkr_gateway',
      ok: gatewayOk,
      label: 'IB Gateway (session READY)',
      detail: gatewayDetail(input, gatewayOk),
      action: gatewayAction,
    },
  ];

  const deskReady = apiOk && enabled && gatewayOk;
  const failStreak = input.apiFailStreak ?? 0;
  const loopWedged = Boolean(input.health?.ib_loop_lag_ms?.wedged);
  const sustainedApiDown = !apiOk && failStreak >= DESK_API_FAIL_STREAK_FOR_OVERLAY;
  const inFlight = Boolean(input.deskActionInFlight);

  return {
    items,
    deskReady,
    tradeReady: deskReady,
    blockDesk: !deskReady,
    autoOverlay: (loopWedged || sustainedApiDown) && !inFlight,
  };
}
