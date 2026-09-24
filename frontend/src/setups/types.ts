/** Wire shapes of `/ws/setups` and `/api/setups/*` (backend `setup_scanner/`, ADR 022). */
import type { CatalystVerdict } from '../types/catalystVerdict';

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
  /** The first-pullback template in play: the one that proposes. */
  template?: { id: string; rev: number; name: string } | null;
  templates_watched?: number;
  replay?: SetupsReplay | null;
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
