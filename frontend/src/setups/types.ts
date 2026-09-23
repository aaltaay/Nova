/** Wire shapes of `/ws/setups` and `/api/setups/*` (backend `setup_scanner/`, ADR 022). */

export type SetupState = 'near' | 'armed' | 'triggered' | 'pullback' | 'leg' | 'failed' | 'watching';
export type TapeVerdict = 'go' | 'wait' | 'veto' | 'blind';

export interface SetupLevels {
  leg_t?: number;
  trigger: number;
  entry: number;
  stop: number;
  risk: number;
  target1: number;
  pullback_bars: number;
  leg_high: number;
  leg_low: number;
  leg_pct: number;
  armed_at?: number;
  kind?: string;
  triggered_at?: number;
  nth?: number;
}

export interface TapeRead {
  verdict: TapeVerdict;
  reasons: string[];
  line?: { depth: boolean; tape: boolean } | null;
  metrics?: Record<string, number | boolean | null> | null;
}

export interface SetupProposal {
  id: string;
  setup_id: string;
  symbol: string;
  kind: string | null;
  trigger: number | null;
  entry: number | null;
  stop: number | null;
  target1: number | null;
  risk: number | null;
  grade: string | null;
  reasons: string[] | null;
  created_at: number;
  status: string;
  tape_now?: TapeVerdict;
}

/** The catalyst classifier's verdict at arm time (ADR 024): the same rules as the backfilled history. */
export interface SetupCatalyst {
  verdict: 'catalyst' | 'negative' | 'routine_only' | 'noise_only' | 'none_found' | 'not_checked';
  category: string | null;
  strength: 'strong' | 'weak' | null;
  title: string | null;
  source: string | null;
  published_ts: number | null;
  url: string | null;
  negative_too: boolean;
  rules_version: string;
  /** Sources that looked across the whole window (alpaca, edgar, globenewswire, prnewswire, newsfile). */
  sources_answered?: string[];
  /** A Nasdaq T1 / T12 halt inside the window with no resumption yet: the news is coming. */
  news_pending?: boolean;
  halt_code?: string | null;
}

export interface SetupPillars {
  price: number | null;
  change_pct: number | null;
  rvol: number | null;
  float: number | null;
  /** True only for a real catalyst; null when no catalyst read covered the moment. */
  news: boolean | null;
  headline: string | null;
  catalyst?: SetupCatalyst | null;
  checks?: Record<string, boolean | null>;
}

export interface SetupRow {
  symbol: string;
  state: SetupState;
  reason: string;
  kind: string | null;
  nth: number;
  setup_id: string | null;
  setup: SetupLevels | null;
  leg: { t: number; high: number; low: number; pct: number } | null;
  last_price: number | null;
  distance: number | null;
  grade: string | null;
  pillars: SetupPillars | null;
  tape: TapeRead | null;
  proposal: SetupProposal | null;
  outcome: string | null;
  bar_r: number | null;
  mfe: number | null;
  mae: number | null;
}

export interface SetupsBoard {
  schema_version: number;
  generated_at: number;
  session_date: string | null;
  universe: number;
  seeding: number;
  scoreboard: boolean;
  scoreboard_error: string | null;
  proposing: boolean;
  rows: SetupRow[];
  proposals: SetupProposal[];
}

export interface ScoreStats {
  armed: number;
  triggered: number;
  trigger_rate: number | null;
  target_first: number;
  stop_first: number;
  open: number;
  scored: number;
  win_pct: number | null;
  avg_r: number | null;
  avg_net_r: number | null;
  avg_mfe_r: number | null;
  avg_mae_r: number | null;
}

export interface Scoreboard {
  days: number;
  date_from: string | null;
  row_count: number;
  summary: { all: ScoreStats; by: Record<string, Record<string, ScoreStats>> };
}
