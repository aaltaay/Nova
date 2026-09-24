import type { WatchlistEntry } from '../strategy/types';
import type { CatalystVerdict } from './catalystVerdict';

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
  /** Null when unknown -- a name-only row (no quote yet) has no volume, not 0. */
  volume: number | null;
  rel_volume: number | null;
  /** Which average-volume source `rel_volume` divides by ('yfinance' | 'alpaca'); absent when unreported. */
  rvol_source?: string | null;
  /** 'close_fallback' when the price is IBKR's prior close (no trade yet) -- never a live print. */
  quote_quality?: string | null;
  has_news: boolean;
  /** Sim playback (ADR 023): the recorded row did not know whether there was news -- `has_news` is not "no news". */
  news_unknown?: boolean;
  /** Sim playback (ADR 023): halted at the board's minute per the halt log; null = unknown. Absent on live rows. */
  halted?: boolean | null;
  newest_headline_at: string | null;
  /** What the news since the prior close is (ADR 024): null = not read yet; absent on played-back rows. */
  catalyst?: CatalystVerdict | null;
  market_cap: number | null;
  float: number | null;
  /** Yahoo's shares outstanding (#532); null when unknown, absent from an older API. */
  shares_outstanding?: number | null;
  /** True when Yahoo's own shares outstanding or short interest contradicts `float` (#532); null = not checkable. */
  float_contradicted?: boolean | null;
  /** Why the float is doubtful, only when `float_contradicted` is true. */
  float_contradicted_reason?: string | null;
  short_interest: number | null;
  /** Epoch seconds of the FINRA settlement `short_interest` is from (Yahoo's date); null when unknown. */
  short_interest_ts?: number | null;
  /** Yahoo's own ratio (short interest over Yahoo's average volume), not FINRA's days to cover. */
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
