import type { DepthLevel } from '../ibkr/types';

/**
 * A Level 2 book the local recorder archived for the replayed session (#309).
 * Present only where `l2.db` actually covered the playhead second; the replay
 * never synthesises one, so its absence is `null`, not an empty book.
 */
export interface HistoricalDepthBook {
  symbol: string;
  bids: DepthLevel[];
  asks: DepthLevel[];
  /** Epoch seconds the book was recorded at (at or before the playhead). */
  ts: number;
  /** Playhead second minus `ts`. */
  age_sec: number;
  l1_fallback: boolean;
  session_id?: string | null;
  /** Which archive served it, e.g. `l2_recorder`. */
  source: string;
}

export interface HistoricalWindow { symbol: string; date: string; start: string; end: string }

/**
 * Where a window's tape comes from (ADR 046): `massive` -- imported from the
 * operator's Massive flat files (trades to the nanosecond, 1-minute bars, the
 * NBBO); anything else -- an IBKR download (whole-second trades, no quotes).
 */
export const MASSIVE_SOURCE = 'massive';
/**
 * A Massive window's bid / ask: `complete` (imported), `none` (the ticker had no
 * quote in the window), `not_downloaded` (the day's quotes file is not on disk yet).
 */
export type MassiveQuoteStatus = 'complete' | 'none' | 'not_downloaded';

export interface HistoricalSelection extends HistoricalWindow {
  /** Window bounds, epoch seconds (the backend's `store.window` spec). */
  start_ts?: number;
  end_ts?: number;
  coverage_through: number;
  /** Downloaded ranges, [start, end) epoch seconds -- may have gaps (playhead-first). */
  coverage?: number[][];
  covered_seconds?: number;
  trade_count?: number;
  download_status?: string;
  job_id?: string | null;
  /** `massive` for a window imported from the Massive files; `ibkr_historical` (or absent) for an IBKR download. */
  source?: string;
  /** A Massive window's bid / ask, its quote rows and its 1-minute bars; absent on an IBKR download. */
  quote_status?: MassiveQuoteStatus | null;
  quote_count?: number;
  bar_count?: number;
}
export interface HistoricalJob extends HistoricalWindow {
  /** `count` / `pages` are null when the payload did not carry a number (parsed at the boundary, C7). */
  id: string; kind: string; status: string; count: number | null; pages: number | null; error: string | null;
  cursor?: number; start_ts?: number; end_ts?: number; volume?: number; updated?: number;
  progress_pct?: number; downloaded_through?: number; eta_seconds?: number | null;
  stale?: boolean; age_seconds?: number; started?: number;
  coverage?: number[][]; covered_seconds?: number;
  /** `massive` for an import from the Massive files (ADR 046); absent for an IBKR download. */
  source?: string;
  /** A running import's step (`reading`, `saving`) and each file's share read, 0-100. */
  stage?: string | null;
  stages?: Record<string, number> | null;
  quote_status?: MassiveQuoteStatus | null;
  quote_count?: number;
  bar_count?: number;
}
/** The listing's `massive` block: is the folder there, and how many days can replay. */
export interface MassiveSummary {
  available: boolean;
  reason: string | null;
  trade_days: number;
  /** Days whose trades and bid / ask are both on disk. */
  quote_days: number;
  first: string | null;
  last: string | null;
  /** When `last`'s trades file was finished on disk (epoch seconds); null when unknown or an older API. */
  last_landed?: number | null;
  /** The import store could not be read, so its imports are not listed (null when it was). */
  store_error: string | null;
}
/** One day of `GET /api/sim/history/massive/days`: which of its files are whole on disk. */
export interface MassiveDay { date: string; trades: boolean; quotes: boolean; minute_aggs: boolean }
export interface MassiveDays { available: boolean; reason: string | null; days: MassiveDay[] }
export interface HistoricalStatus {
  jobs: HistoricalJob[];
  selection?: HistoricalSelection | null;
  default_date?: string;
  /** Absent from an API older than ADR 046. */
  massive?: MassiveSummary | null;
}

export const isMassive = (row: { source?: string | null } | null | undefined): boolean =>
  row?.source === MASSIVE_SOURCE;
