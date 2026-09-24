/** Advise rail copy and tunables. Feature-local -- do not add to the barrel. */

export const ADVISE_DEFAULT_DEPTH = 2;
export const ADVISE_MIN_DEPTH = 1;
export const ADVISE_MAX_DEPTH = 5;
export const ADVISE_ESTIMATE_DEBOUNCE_MS = 300;

export function clampAdviseDepth(depth: number): number {
  const value = Number.isFinite(depth) ? Math.trunc(depth) : ADVISE_DEFAULT_DEPTH;
  return Math.max(ADVISE_MIN_DEPTH, Math.min(ADVISE_MAX_DEPTH, value));
}
export const ADVISE_TITLE = 'Advise';
export const ADVISE_RAIL_LABEL = 'Advise';
export const ADVISE_DISCLAIMER =
  'Advisory only -- not financial advice and not auto-trading. A human always Places in Nova. Advise never sends orders.';
export const ADVISE_MODEL_LABEL = 'Claude Sonnet (latest via OpenRouter)';
export const ADVISE_STALE_NUDGE = 'This run is over ~2 hours old. Refresh?';
export const ADVISE_EMPTY_HINT =
  'Pick a symbol and press Run. Prefill spends no tokens.';
export const ADVISE_AGENTS_HINT =
  'Full set every run: fundamentals, news, sentiment, technical, bull/bear, trader, risk.';

/** Why Run / Force refresh / Cancel / Retry is locked (ux/whyTip.ts). */
export const ADVISE_WHY_NO_SYMBOL = 'Type a symbol first';
export const adviseWhyBadSymbol = (symbol: string): string => `${symbol} is not a ticker symbol`;
/** One flag covers Run, Cancel and Retry: the request sent last has not answered yet. */
export const ADVISE_WHY_BUSY = 'Waiting for Advise to answer the last request';
export const ADVISE_WHY_RUN_LIVE = 'A run is already going -- wait for it, or Cancel it';
export const ADVISE_WHY_NOTHING_TO_CANCEL = 'No run is queued or running -- nothing to cancel';
