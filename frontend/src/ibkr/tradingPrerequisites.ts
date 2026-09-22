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
  PREREQ_COMPLETED_ORDERS_STUCK_DETAIL,
  PREREQ_COMPLETED_ORDERS_STUCK_PREFIX,
  PREREQ_GATEWAY_CLIENT_ID_DETAIL,
  PREREQ_GATEWAY_FOLLOW_LIVE_DETAIL,
  PREREQ_GATEWAY_LEGACY_PAPER_UP_DETAIL,
  PREREQ_GATEWAY_LOGIN_DETAIL,
  PREREQ_GATEWAY_PORT_OPEN_DETAIL,
  PREREQ_GATEWAY_READ_ONLY_DETAIL,
  PREREQ_GATEWAY_READ_ONLY_LABEL,
  PREREQ_GATEWAY_STALE_SECOND_FACTOR_DETAIL,
} from './gatewayUxConstants';

export type PrereqId =
  | 'nova_api'
  | 'ibkr_gateway'
  | 'ibkr_enabled'
  | 'gateway_read_only';

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

/** Amber note under the checklist -- never changes deskReady / blockDesk. */
export interface PrereqWarning {
  id: 'completed_orders';
  label: string;
  detail: string;
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
  /** Legacy caller hint; recording never suppresses connectivity safety. */
  sessionRecording?: boolean;
  /** In-app Sim practice -- Gateway is not required. */
  simMode?: boolean;
  /**
   * Paper or Sim (ADR 020): orders come from Nova's practice ledger, so the
   * IBKR completed-orders notice does not apply even though Paper needs the
   * Gateway for its feed (QA C68).
   */
  practiceOrders?: boolean;
  /** status.completed_orders_unanswered_since (D-058), epoch seconds. */
  completedOrdersUnansweredSince?: number | null;
  /** status.gateway_read_only (D-076) -- the Gateway rejected an order with
   * Error 321 because Read-Only API is ticked. Named blocker, not a login. */
  gatewayReadOnly?: boolean | null;
}

export interface TradingPrerequisites {
  items: PrereqItem[];
  warnings: PrereqWarning[];
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

/** The only Gateway the checklist may switch Nova to. */
export type GatewayFollowTarget = 'live' | null;

/**
 * Live is the one follow target (ADR 020). When Nova targets live and only the
 * legacy paper Gateway (4002) answers, that is not a switch: beside a live
 * login it is read-only and carries no tape, so the row asks for the live
 * login instead (`legacyPaperGatewayUp`).
 */
export function gatewayPortMismatchHint(
  hint: string | null | undefined,
): GatewayFollowTarget {
  if (hint === 'paper_port_refused_live_listening') return 'live';
  return null;
}

export function legacyPaperGatewayUp(hint: string | null | undefined): boolean {
  return hint === 'live_port_refused_paper_listening';
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
  if (input.simMode) {
    return 'Sim practice -- a replayed real session. No Gateway required.';
  }
  if (gatewayOk) {
    return 'Gateway connected -- live prices and order path available.';
  }
  if (input.secondFactorStale) {
    const age = Math.round(input.secondFactorAgeSec ?? 0);
    return `${PREREQ_GATEWAY_STALE_SECOND_FACTOR_DETAIL} (open ${age}s -- IBKR's own limit is 180s.)`;
  }
  if (legacyPaperGatewayUp(input.disconnectHint)) return PREREQ_GATEWAY_LEGACY_PAPER_UP_DETAIL;
  if (gatewayPortMismatchHint(input.disconnectHint) === 'live') return PREREQ_GATEWAY_FOLLOW_LIVE_DETAIL;
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

/**
 * "Completed orders not answering since 01:14 AM" (D-058), or null. Shared by
 * the checklist and the header Desk chip so both say the same thing. Only on
 * a READY, non-Sim desk -- while reconnecting the stamp may already be stale.
 */
export function completedOrdersStuckNotice(input: {
  sinceEpochSec?: number | null;
  gatewayReady: boolean;
  simMode?: boolean;
  /** Injectable "now" for tests; defaults to the wall clock. */
  now?: Date;
}): string | null {
  const since = Number(input.sinceEpochSec);
  if (input.simMode || !input.gatewayReady || !Number.isFinite(since) || since <= 0) {
    return null;
  }
  const at = new Date(since * 1000);
  const today = (input.now ?? new Date()).toDateString() === at.toDateString();
  // Add the weekday once it is not today, so an overnight onset never reads
  // as a time later today.
  const clock = at.toLocaleString([], {
    ...(today ? {} : { weekday: 'short' as const }),
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${PREREQ_COMPLETED_ORDERS_STUCK_PREFIX} ${clock}`;
}

/** Pure builder — unit-test without React. */
export function buildTradingPrerequisites(
  input: TradingPrerequisitesInput,
): TradingPrerequisites {
  const apiOk = novaApiOk(input.health);
  const enabled = input.simMode ? true : input.ibkrEnabled !== false;
  const gatewayOk = input.simMode ? true : Boolean(input.ibkrConnected);
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
      detail: input.simMode
        ? 'Sim practice -- IBKR_ENABLED is not required.'
        : enabled
        ? 'IBKR_ENABLED is on.'
        : 'Set IBKR_ENABLED=true in .env and restart the API.',
      action: enabled ? null : 'env_ibkr',
    },
    {
      id: 'ibkr_gateway',
      ok: gatewayOk,
      label: input.simMode ? 'Sim Feed (no Gateway)' : 'IB Gateway (session READY)',
      detail: gatewayDetail(input, gatewayOk),
      action: gatewayAction,
    },
  ];

  // Only shown once the Gateway has actually rejected an order as read-only.
  // Nova cannot prove the setting is OFF without placing an order, so there is
  // no green counterpart row -- the row simply goes away on the next connect
  // and only comes back if the Gateway rejects again (D-076).
  const readOnly = !input.simMode && input.gatewayReadOnly === true;
  if (readOnly) {
    items.push({
      id: 'gateway_read_only',
      ok: false,
      label: PREREQ_GATEWAY_READ_ONLY_LABEL,
      detail: PREREQ_GATEWAY_READ_ONLY_DETAIL,
      action: 'reconnect_ibkr',
    });
  }

  const warnings: PrereqWarning[] = [];
  const stuckNotice = completedOrdersStuckNotice({
    sinceEpochSec: input.completedOrdersUnansweredSince,
    gatewayReady: gatewayOk,
    simMode: input.simMode || input.practiceOrders,
  });
  if (stuckNotice) {
    warnings.push({
      id: 'completed_orders',
      label: stuckNotice,
      detail: PREREQ_COMPLETED_ORDERS_STUCK_DETAIL,
    });
  }

  // Read-only is part of desk readiness: every order would be rejected. It
  // does not change any spend / order gate -- those stay on the trade path.
  const deskReady = apiOk && enabled && gatewayOk && !readOnly;
  const failStreak = input.apiFailStreak ?? 0;
  const loopWedged = Boolean(input.health?.ib_loop_lag_ms?.wedged);
  const sustainedApiDown = !apiOk && failStreak >= DESK_API_FAIL_STREAK_FOR_OVERLAY;
  const inFlight = Boolean(input.deskActionInFlight);

  return {
    items,
    warnings,
    deskReady,
    tradeReady: deskReady,
    blockDesk: !deskReady,
    autoOverlay: (loopWedged || sustainedApiDown) && !inFlight,
  };
}
