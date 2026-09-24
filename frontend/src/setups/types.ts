/** Wire shapes of `/ws/setups` and `/api/setups/*` (backend `setup_scanner/`, ADR 022, ADR 031). */
import type { CatalystVerdict } from '../types/catalystVerdict';

/** A setup with a scanner (ADR 031): every row, proposal and card names one. */
export type SetupType = 'first_pullback' | 'bull_flag' | 'flat_top_breakout' | 'red_to_green' | string;

/** `filtered`: the pattern armed but the template's stock filter keeps the name out (ADR 029). */
export type SetupState = 'near' | 'armed' | 'triggered' | 'pullback' | 'leg' | 'failed' | 'watching' | 'filtered';
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
  trigger_price?: number;
  nth?: number;
  /** The setup's own facts (ADR 031): the flat top's entry mode and break, the open and its red closes, the pole. */
  detail?: SetupDetail | null;
}

export interface SetupDetail {
  /** Flat-top breakout. */
  entry_mode?: 'hold' | 'break' | string;
  base_low?: number;
  broke_at?: number | null;
  hold_bars?: number;
  hold_bar_t?: number;
  /** Red to green. */
  open?: number;
  open_t?: number;
  red_bars?: number;
  hod?: number;
  /** Bull flag. */
  pole_bars?: number;
  flag_bars?: number;
  pole_volume?: number;
  flag_volume?: number;
  volume_known?: boolean;
}

/** The tape flow score riding on a tape read (ADR 034): -1 sellers .. +1 buyers. */
export interface TapeFlow {
  score: number | null;
  label: string;
  readings?: Record<string, number | null> | null;
}

export interface TapeRead {
  verdict: TapeVerdict;
  reasons: string[];
  line?: { depth: boolean; tape: boolean } | null;
  metrics?: Record<string, number | boolean | string | null> | null;
  flow?: TapeFlow | null;
}

export interface SetupProposal {
  id: string;
  setup_id: string;
  /** ADR 031: the setup that raised it (absent on an older API: the first pullback). */
  setup_type?: SetupType;
  template_name?: string | null;
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
export type SetupCatalyst = CatalystVerdict;

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
  /** ADR 031: which setup's scanner holds this row (absent on an older API: the first pullback). */
  setup_type?: SetupType;
  state: SetupState;
  reason: string;
  kind: string | null;
  nth: number;
  setup_id: string | null;
  setup: SetupLevels | null;
  /** The setup's context: the leg, the pole, the impulse into the high of day, or the open and the red phase. */
  leg: { t: number; high: number; low: number; pct: number; bars?: number } | null;
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
  failed_at?: number | null;
}

/** Today's funnel for one setup's card (ADR 031). */
export interface SetupCounts {
  watching: number;
  forming: number;
  armed: number;
  near: number;
  triggered: number;
  failed: number;
  filtered: number;
  proposed: number;
}

/** One setup with a scanner on the board (ADR 031): its level, template, window and today's counts. */
export interface SetupSummary {
  id: SetupType;
  level: number;
  chosen: boolean;
  proposing: boolean;
  template: { id: string; rev: number; name: string; params_hash?: string } | null;
  templates_watched: number;
  window: { start: string; end: string; state: 'before' | 'open' | 'after' | string };
  counts: SetupCounts;
}

/** The Sim eyes' replay (ADR 029): what the board follows off the live edge. */
export interface SetupsReplay {
  kind: 'capture' | 'historical';
  date: string | null;
  symbol: string | null;
  playhead: number | null;
  at: number | null;
  loading: boolean;
  error: string | null;
  /** Why the eyes cannot watch this replay (a download has no Level 2). */
  note: string | null;
}

export interface SetupsBoard {
  schema_version: number;
  generated_at: number;
  session_date: string | null;
  /** `live` (the market) or `sim` (the Sim eyes over the loaded Session Record, ADR 029). */
  source?: 'live' | 'sim';
  /** ADR 031: one summary per setup with a scanner (schema 2). */
  setups?: SetupSummary[];
  replay?: SetupsReplay | null;
  universe: number;
  /** The symbols the scanner follows now, sorted (the HOD Momo names); absent on an API before 2026-09-24. */
  universe_symbols?: string[];
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
  /** ADR 031: the setup the scoreboard answers for. */
  setup_type?: SetupType;
  days: number;
  date_from: string | null;
  row_count: number;
  summary: { all: ScoreStats; by: Record<string, Record<string, ScoreStats>> };
}
