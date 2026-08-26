/**
 * Backstop for a pane whose one-shot /bars fetch returned empty+filling and
 * has no periodic reconciliation poll (e.g. 10Sec -- see CHART_REFETCH_SEC).
 * The normal recovery path is a bars_patch WebSocket push once the
 * background historical fill completes (see useTickerStream). If that push
 * is missed (subscribe race, drop, reconnect), this keeps retrying the
 * HTTP fetch forever at a capped interval -- never a fixed attempt count
 * that gives up and leaves the pane stuck on "Loading IBKR historical...".
 */

export interface StuckBarsRetryState {
  filling: boolean;
  hasBars: boolean;
  chartActive: boolean;
}

export function isStuckLoadingBars({ filling, hasBars, chartActive }: StuckBarsRetryState): boolean {
  return chartActive && filling && !hasBars;
}

export function nextStuckRetryDelayMs(currentDelayMs: number, minMs: number, maxMs: number): number {
  return Math.min(Math.max(currentDelayMs * 2, minMs), maxMs);
}
