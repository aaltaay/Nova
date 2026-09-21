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
}
export interface HistoricalJob extends HistoricalWindow {
  id: string; kind: string; status: string; count: number; pages: number; error: string | null;
  cursor?: number; start_ts?: number; end_ts?: number; volume?: number; updated?: number;
  progress_pct?: number; downloaded_through?: number; eta_seconds?: number | null;
  stale?: boolean; age_seconds?: number; started?: number;
  coverage?: number[][]; covered_seconds?: number;
}
export interface HistoricalStatus {
  jobs: HistoricalJob[];
  selection?: HistoricalSelection | null;
  default_date?: string;
}
