/** Phase K shortability UI copy (ADR 009). */

export const SHORTABILITY_LABEL = 'Short';

export const SHORTABILITY_CHIP_TOOLTIP =
  'IBKR tick 236 estimate -- confirm fee / locate in TWS before shorting. Not Alpaca ETB.';

/** Chip only -- listing.ibkr not on the ticker payload yet (not a real Unknown). */
export const SHORTABILITY_LOADING_LABEL = 'Loading...';

export const SHORTABILITY_LOADING_TOOLTIP =
  'Waiting for IBKR shortability (tick 236) on this symbol.';

export const SHORTABILITY_STATE_LABELS: Record<string, string> = {
  shortable_est: 'Available',
  thin: 'Thin',
  htb_likely: 'HTB',
  unknown: 'Unknown',
};

export const SHORTABILITY_SHORT_DISABLED =
  'Short entry locked (IBKR_SHORT_ENABLED is false)';

export const SHORTABILITY_NOT_SHORTABLE =
  'Not shortable for Nova orders (refresh listing or check TWS)';

export const SHORTABILITY_STALE =
  'Shortability stale -- wait for a fresh listing tick';

export const TICKER_TRADE_LABEL_DIRECTION = 'Direction';
export const TICKER_TRADE_LABEL_LONG = 'Long';
export const TICKER_TRADE_LABEL_SHORT = 'Short';
