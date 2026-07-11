/** TypeScript interfaces for the Strategy / Watchlist tab. Mirrors backend/strategy/*.py to_dict() shapes. */

export interface PillarCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface FivePillarsResult {
  symbol: string;
  all_pass: boolean;
  pass_count: number;
  total: number;
  checkmark: string;
  pillars: PillarCheck[];
}

export interface WatchlistSubScores {
  change_pct: number;
  relative_volume: number;
  float: number;
  catalyst: number;
}

export interface WatchlistEntry {
  symbol: string;
  composite_score: number;
  sub_scores: WatchlistSubScores;
  five_pillars: FivePillarsResult;
}

export interface WatchlistResponse {
  note: string;
  count: number;
  entries: WatchlistEntry[];
}

/** Shape shared by gap_and_go / bull_flag / abcd to_dict() — see backend/strategy/*.py. */
export interface SetupSignalDetail {
  symbol: string;
  eligible: boolean;
  would_execute: false;
  triggered: boolean;
  current_price: number | null;
  entry_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  five_pillars: FivePillarsResult;
  notes: string[];
  [key: string]: unknown;
}

export type SetupName = 'gap_and_go' | 'bull_flag' | 'abcd';

export interface SetupsResponse {
  note: string;
  symbol: string;
  eligible_setups: SetupName[];
  any_eligible: boolean;
  gap_and_go: SetupSignalDetail;
  bull_flag: SetupSignalDetail;
  abcd: SetupSignalDetail;
}

/** One broadcast frame from /ws/strategy: the triggering setup's detail + metadata. */
export interface SetupSignal extends SetupSignalDetail {
  setup: SetupName;
  timestamp: number; // unix seconds
}
