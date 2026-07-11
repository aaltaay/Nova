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

/** Mirrors backend/journal/*.py row + metrics shapes. */
export interface JournalSignalRow {
  id: number;
  ts: number; // unix seconds
  symbol: string;
  setup: SetupName;
  entry_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  payload_json: string;
}

export interface JournalTradeRow {
  id: number;
  opened_ts: number;
  closed_ts: number | null;
  symbol: string;
  setup: string | null;
  side: string;
  qty: number;
  entry_price: number;
  exit_price: number | null;
  stop_price: number | null;
  target_price: number | null;
  pnl: number | null;
  adherent: number | null;
  notes: string;
  is_mock: number;
}

export interface GoNoGoCriterion {
  met: boolean | null;
  label: string;
  value: number | null;
}

export interface GoNoGo {
  overall_go: boolean;
  criteria: {
    min_sample_size: GoNoGoCriterion;
    profit_loss_ratio: GoNoGoCriterion;
    adherence: GoNoGoCriterion;
  };
}

export interface JournalMetrics {
  includes_mock_data: boolean;
  total_closed_trades: number;
  win_rate_pct: number | null;
  avg_win_dollars: number | null;
  avg_loss_dollars: number | null;
  profit_loss_ratio: number | null;
  total_pnl_dollars: number | null;
  adherence_pct: number | null;
  go_no_go: GoNoGo;
}

/** Mirrors backend/strategy/risk.py RiskState.to_dict(). */
export interface RiskStatus {
  session_date: string;
  daily_realized_pnl: number;
  peak_daily_pnl: number;
  consecutive_losses: number;
  consecutive_wins: number;
  trades_today: number;
  can_trade: boolean;
  halt_reason: string | null;
  position_size_shares: number;
  daily_goal_dollars: number;
}

/** Mirrors backend/strategy/executor.py OpenPosition (as returned by status()). */
export interface ExecutorOpenPosition {
  symbol: string;
  setup: string;
  qty: number;
  entry_price: number;
  stop_price: number;
  target_price: number;
  opened_ts: number;
}

/** Mirrors backend/strategy/executor.py status(). */
export interface ExecutorStatus {
  disclosure: string;
  armed: boolean;
  kill_switch_tripped: boolean;
  ibkr_connected: boolean;
  ibkr_mode: string;
  open_positions: ExecutorOpenPosition[];
}
