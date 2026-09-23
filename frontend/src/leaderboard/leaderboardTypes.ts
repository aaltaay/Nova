/**
 * Wire shapes of the scanner leaderboard routes (AGENTS.md section 3, ADR 022)
 * and the playback state the Scanner board reads. Every unknown is null.
 */
import type { ScannerRow } from '../types/scanner';

export type LeaderboardSource = 'recorded' | 'reconstructed';

/** One leaderboard row: the board as it stood at `minute_ts`. `change_pct` / `gap_pct` are fractions. */
export interface LeaderboardRow {
  symbol: string;
  minute_ts: number | null;
  board: string;
  source: string | null;
  rank: number | null;
  price: number | null;
  prev_close: number | null;
  change_pct: number | null;
  volume: number | null;
  rvol: number | null;
  rvol_basis: 'daily_avg' | 'time_of_day_20' | null;
  float_shares: number | null;
  has_news: boolean | null;
  news_first_seen_ts: number | null;
  halted: boolean | null;
  gap_pct: number | null;
  exchange: string | null;
  market_cap: number | null;
}

/** Why there is no board at the playhead; `start` / `end` are null outside the session. */
export interface LeaderboardGap {
  reason: string;
  start: number | null;
  end: number | null;
  /** For `not_running`: how the run before it ended (`shutdown` | `unexpected`), else null. */
  stop: string | null;
}

export interface LeaderboardBoard {
  state: string | null;
  rows: LeaderboardRow[];
}

/** `GET /api/leaderboard/{date}?at=` */
export interface LeaderboardAt {
  date: string;
  at: number | null;
  source: LeaderboardSource | null;
  minute_ts: number | null;
  covered: boolean;
  gap: LeaderboardGap | null;
  boards: Record<string, LeaderboardBoard>;
  leaders: string[];
}

export interface LeaderboardDaySummary {
  minutes: number | null;
  first_ts: number | null;
  last_ts: number | null;
}

export interface LeaderboardDay {
  date: string;
  recorded: LeaderboardDaySummary | null;
  reconstructed: LeaderboardDaySummary | null;
}

/** `GET /api/leaderboard/days` (newest first). */
export interface LeaderboardDays {
  store: { path: string | null; ok: boolean; error: string | null };
  days: LeaderboardDay[];
}

export interface LeaderboardCoverageGap {
  start: number;
  end: number;
  reason: string;
}

/** `GET /api/leaderboard/{date}/coverage` (whole epoch seconds). */
export interface LeaderboardCoverage {
  date: string;
  source: LeaderboardSource | null;
  session_open: number | null;
  session_close: number | null;
  spans: number[][];
  gaps: LeaderboardCoverageGap[];
}

/** The Scanner lists a played-back board fills. */
export type ReplayListKey = 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'large_cap';

export interface ScannerReplayTables {
  gappers: ScannerRow[];
  gainers: ScannerRow[];
  losers: ScannerRow[];
  afterhours: ScannerRow[];
  largeCap: ScannerRow[];
}

/**
 * What the Scanner shows while it follows the Sim playhead. `minute` is the
 * playhead minute the board was asked for; `minuteTs` the board's own minute
 * once one answered. In a gap, while loading and after a failure the tables
 * are empty -- a board from another minute is never carried in.
 */
export interface ScannerReplay {
  date: string;
  minute: number;
  status: 'loading' | 'ready' | 'error';
  source: LeaderboardSource | null;
  minuteTs: number | null;
  gap: LeaderboardGap | null;
  error: string | null;
  tables: ScannerReplayTables;
  /** Board lists the answer carries, with their coverage state. */
  boardStates: Partial<Record<string, string | null>>;
  leaders: string[];
}
