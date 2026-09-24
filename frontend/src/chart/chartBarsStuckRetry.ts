/**
 * Backstop for a pane whose one-shot /bars fetch returned empty+filling and
 * has no periodic reconciliation poll (e.g. 10Sec -- see CHART_REFETCH_SEC).
 * The normal recovery path is a bars_patch WebSocket push once the
 * background historical fill completes (see useTickerStream). If that push
 * is missed (subscribe race, drop, reconnect), this keeps retrying the
 * HTTP fetch forever at a capped interval -- never a fixed attempt count
 * that gives up and leaves the pane stuck on "Loading IBKR historical...".
 * Each retry is a local `/bars` read: while IBKR history is not answering the
 * backend holds the resend back for a short backoff and the coverage's
 * `last_error` makes the pane say so (#555, ChartFillingStatus.tsx).
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

export function startStuckBarsRetries(
  retry: () => void,
  minMs: number,
  maxMs: number,
): () => void {
  let stopped = false;
  let delayMs = minMs;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const schedule = () => {
    timer = setTimeout(() => {
      if (stopped) return;
      retry();
      delayMs = nextStuckRetryDelayMs(delayMs, minMs, maxMs);
      schedule();
    }, delayMs);
  };

  schedule();
  return () => {
    stopped = true;
    if (timer !== null) clearTimeout(timer);
  };
}
