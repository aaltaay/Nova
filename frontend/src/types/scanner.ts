import type { WatchlistEntry } from '../strategy/types';

/** Shared row shape for the Gappers / Movers / After Hours scanner tables. */
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
  /** Joined client-side from GET /api/strategy/watchlist by symbol (see useWatchlistOverlay).
   * Null/undefined when the symbol isn't currently ranked in the watchlist. */
  watchlist?: WatchlistEntry | null;
  /** Flat mirror of watchlist.composite_score so the generic column sorter (App.tsx
   * sortedArray) can sort on a primitive — same pattern as change_pct/change_abs. */
  watchlist_score?: number | null;
}

// Legacy aliases — kept for any remaining narrower references
export type Gapper = ScannerRow;
export type Mover = ScannerRow;
export type Afterhours = ScannerRow;

export type SortDir = 'asc' | 'desc' | null;
export interface SortConfig { key: string; dir: SortDir; }
