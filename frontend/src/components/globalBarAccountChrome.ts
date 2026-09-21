/**
 * Account cluster state for GlobalAppBar.
 *
 * GATEWAY chip = market-data session. Account cluster = Net Liq / Day P&L poll.
 * Those must never contradict: do not label "IBKR offline" while Gateway is up.
 */

export type AccountChromeState = 'offline' | 'loading' | 'unavailable' | 'ready';

export function resolveAccountChromeState(opts: {
  ibkrConnected: boolean;
  /** summary.connected from /api/ibkr/account; undefined when no summary yet */
  summaryConnected: boolean | undefined;
  loading: boolean;
  error: string | null;
}): AccountChromeState {
  if (!opts.ibkrConnected) return 'offline';
  if (opts.summaryConnected) return 'ready';
  // Gateway up but account snapshot missing or explicitly disconnected.
  if (opts.error) return 'unavailable';
  // First paint / in-flight poll — placeholders, not a scare chip.
  return 'loading';
}

/**
 * Practice venues (ADR 020): Nova's ledger is THE account there, so the
 * cluster follows the practice poll rather than the IBKR summary -- Paper runs
 * on the live Gateway, so an IBKR summary may exist beside it. The ledger has
 * no Gateway to lose, so it is never "offline"; the GATEWAY chip reports the
 * feed. A snapshot from the other practice venue counts as not loaded yet.
 */
export function resolvePracticeChromeState(opts: {
  venue: string;
  data: { venue: string } | null;
  error: string | null;
}): AccountChromeState {
  if (opts.data && opts.data.venue === opts.venue) return 'ready';
  return opts.error ? 'unavailable' : 'loading';
}
