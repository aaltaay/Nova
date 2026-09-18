/** Shared scanner/desk column roles for stable live widths.
 *
 * Auto-layout tables reflow when PRICE / CHANGE / GAP % digit counts change.
 * Role classes + reserved widths (scanner-table-cols.css) lock those columns
 * on every table that uses the scanner shell. Width strings are the CSS
 * contract -- keep them identical to scanner-table-cols.css.
 */

export const SCANNER_TABLE_WRAPPER_CLASS = 'table-wrapper table-wrapper--scanner';

export const SCANNER_COL_WIDTH = {
  price: 'calc(10ch + 1.2rem)',
  pct: 'calc(10ch + 1.2rem)',
  num: 'calc(9ch + 1.2rem)',
  compact: 'calc(5ch + 1.1rem)',
  rownum: '2.4em',
} as const;

export type ScannerColRole = 'num' | 'pct' | 'price' | 'compact' | 'flex' | 'chrome';

/** Column key -> layout role. Unknown keys fail open as flex (absorb leftover). */
export const SCANNER_COL_ROLE: Record<string, ScannerColRole> = {
  newest_headline_at: 'chrome',
  symbol: 'chrome',
  earnings_day_offset: 'chrome',
  watchlist_score: 'chrome',
  status: 'chrome',
  price: 'price',
  current_price: 'price',
  prev_close: 'price',
  previous_close: 'price',
  high_20d: 'price',
  change_pct: 'pct',
  gap_percent: 'pct',
  change_5d_pct: 'pct',
  change_20d_pct: 'pct',
  volume: 'flex',
  catalyst_headline: 'flex',
  float: 'num',
  short_interest: 'num',
  market_cap: 'num',
  rvol: 'num',
  atr_expansion: 'num',
  spike_ratio: 'num',
  spike_shares: 'num',
  large_cap_score: 'compact',
  days_to_earnings: 'compact',
  age_sec: 'compact',
};

const NUMERIC_ROLES = new Set<ScannerColRole>(['num', 'pct', 'price', 'compact']);

export function scannerColRole(key: string): ScannerColRole {
  return SCANNER_COL_ROLE[key] ?? 'flex';
}

export function scannerColClass(key: string): string {
  const role = scannerColRole(key);
  const safe = key.replace(/[^a-z0-9_-]/gi, '-');
  return `scanner-col scanner-col--${role} scanner-col--${safe}`;
}

export function isScannerNumericCol(key: string): boolean {
  return NUMERIC_ROLES.has(scannerColRole(key));
}
