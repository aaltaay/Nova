/** Shared scanner-table column tuples.
 *
 * News and Earnings are one definition used by Gappers / Gainers / Losers /
 * Afterhours *and* Large Cap. Do not copy the tuples -- import these constants.
 * The key must match the ScannerRow field name; the label is the header text.
 *
 * Dense layout: Change combines change_pct/change_abs, Volume combines
 * volume/rel_volume, Pillars combines watchlist_score with the Five Pillars
 * checkmark, and Short Int. combines short_interest/short_ratio
 * (see renderCell in components/ScannerTableRow.tsx). Sort keys stay on the
 * primary field. Pillars is joined client-side from the Contenders tab
 * (strategy/useWatchlistOverlay.ts). It was headed "Watch" until the
 * operator's own Watch list (watch_list/) took that word.
 */

export const SCANNER_NEWS_COLUMN: [string, string] = ['newest_headline_at', 'News'];
export const SCANNER_EARNINGS_COLUMN: [string, string] = ['earnings_day_offset', 'Earnings'];

/** Scanner sort keys holding ISO times: text, but their first click is newest first. */
export const SCANNER_TIME_SORT_KEYS: ReadonlySet<string> = new Set([SCANNER_NEWS_COLUMN[0]]);

export const SCANNER_COLUMNS: [string, string][] = [
  SCANNER_NEWS_COLUMN,
  ['symbol', 'Symbol'],
  SCANNER_EARNINGS_COLUMN,
  ['price', 'Price'],
  ['change_pct', 'Change'],
  ['gap_percent', 'Gap %'],
  ['volume', 'Volume · RVOL'], // label mirrored in market_ui.SCANNER_VOLUME_COLUMN_LABEL
  ['watchlist_score', 'Pillars'],
  ['float', 'Float'],
  ['short_interest', 'Short Int.'],
  ['market_cap', 'Mkt Cap'],
];

// Large Cap swing table (ADR 014): RVOL / ATR / 5d & 20d / score, plus the
// shared News flame and Earnings dots. days_to_earnings stays as Days so the
// swing countdown is not a second "Earnings" header. Default sort is 'rvol'
// descending (ScannerTabPanels).
export const LARGE_CAP_COLUMNS: [string, string][] = [
  SCANNER_NEWS_COLUMN,
  ['symbol', 'Symbol'],
  SCANNER_EARNINGS_COLUMN,
  ['price', 'Price'],
  ['change_pct', 'Change'],
  ['rvol', 'RVOL'],
  ['atr_expansion', 'ATR Exp.'],
  ['change_5d_pct', '5D'],
  ['change_20d_pct', '20D'],
  ['high_20d', '20D High/Low'],
  ['large_cap_score', 'Score'],
  ['days_to_earnings', 'Days'],
  ['market_cap', 'Mkt Cap'],
];
