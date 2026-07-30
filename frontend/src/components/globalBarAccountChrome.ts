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
