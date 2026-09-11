import type { WatchlistEntry } from '../strategy/types';

/** Shared row shape for Gappers / Movers / After Hours / Large Cap tables. */
export interface ScannerRow {
  symbol: string;
  /** Listing venue from Alpaca assets (e.g. NASDAQ, NYSE, ARCA, AMEX). */
  exchange?: string | null;
  /** IB scanner rank for this batch (1 = top of the ranked scan). */
  rank?: number;
  /** Null until the first L1 tick. A newly admitted scanner name is a real row
   * with no quote yet (ADR 010 decision 5) -- never render it as 0.00. */
  price: number | null;
  prev_close: number | null;
  change_pct: number | null;
  change_abs: number | null;
  gap_percent: number | null;
  volume: number;
  rel_volume: number | null;
  has_news: boolean;
  newest_headline_at: string | null;
  market_cap: number | null;
  float: number | null;
  short_interest: number | null;
  short_ratio: number | null;
  /** Yahoo event-of-record date (ET), used by the Earnings dots hover. */
  earnings_date?: string | null;
  /** +1 tomorrow, 0 today, -1 yesterday; null outside the 1-day window. */
  earnings_day_offset?: number | null;
  /** 'bmo' | 'amc' | 'intraday' from the Yahoo timestamp hour in ET. */
  earnings_session?: 'bmo' | 'amc' | 'intraday' | null;
  earnings_estimated?: boolean | null;
  /** Joined client-side from GET /api/strategy/watchlist by symbol (see useWatchlistOverlay).
   * Null/undefined when the symbol isn't currently ranked in the watchlist. */
  watchlist?: WatchlistEntry | null;
  /** Flat mirror of watchlist.composite_score so the generic column sorter (App.tsx
   * sortedArray) can sort on a primitive — same pattern as change_pct/change_abs. */
  watchlist_score?: number | null;

  // ── Large Cap swing table only (ADR 014) — undefined on every other table. ──
  /** Pace RVOL (today's volume vs. expected-by-now from the average). */
  rvol?: number | null;
  /** abs(price - prev_close) / ATR(14) -- today's move relative to its own range. */
  atr_expansion?: number | null;
  change_5d_pct?: number | null;
  change_20d_pct?: number | null;
  high_20d?: number | null;
  low_20d?: number | null;
  /** Composite percentile-rank score (0-100), null until >=1 component is present. */
  large_cap_score?: number | null;
  score_completeness?: number | null;
  days_to_earnings?: number | null;
}

// Legacy aliases — kept for any remaining narrower references
export type Gapper = ScannerRow;
export type Mover = ScannerRow;
export type Afterhours = ScannerRow;

export type SortDir = 'asc' | 'desc' | null;
export interface SortConfig { key: string; dir: SortDir; }
