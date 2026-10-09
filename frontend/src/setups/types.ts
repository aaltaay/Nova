/** Wire shapes of `/ws/setups` and `/api/setups/*` (backend `setup_scanner/`, ADR 022, ADR 031). */
import type { CatalystVerdict } from '../types/catalystVerdict';
import type { LiquidityRead } from './liquidity';

/** A setup with a scanner (ADR 031): every row, proposal and card names one. */
export type SetupType =
  'first_pullback' | 'bull_flag' | 'flat_top_breakout' | 'flat_top_5m' | 'red_to_green' | 'gap_and_go' | string;

/** ADR 049: which way a setup trades. A short setup sells at its entry and covers under it. */
export type SetupSide = 'long' | 'short';
/** Reg SHO's short-sale restriction at a short setup's trigger, else at its arm; null on a long row. */
export type SsrState = 'on' | 'off' | 'unknown';

/** A short setup's five-year test (ADR 049 section 12), as its card and its On lock read it. Its result file is
 *  written by `research/shorts/test_shorts.py` on the desk, never by an agent. */
export interface ShortTest {
  state: 'queued' | 'running' | 'passed' | 'failed' | 'error' | string;
  /** The words the card shows ("five-year test queued: run `py -3 ...`"). */
  text: string;
  rules_hash: string | null;
  /** Whether the tested rules are the template in play's; null before a result exists. */
  matches: boolean | null;
  started_at?: number | null;
  updated_at?: number | null;
  finished_at?: number | null;
  summary?: { trades: number | null; pf: number | null; pf_2x: number | null; exp_r: number | null;
    p: number | null } | null;
  file?: string;
}

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
  /** Backside lower high (ADR 049): the bounce under the fade. */
  bounce_bars?: number;
  bounce_high?: number;
  /** Failed breakout: the flat top it poked over and failed back under; the SSR bounce: the level it rests under. */
  level?: number;
  poke_t?: number;
  failed_bar_t?: number;
  /** Lost VWAP: VWAP at the arm, the candle that lost it and the retest that failed. */
  vwap?: number;
  loss_t?: number;
  retest_t?: number;
  /** SSR bounce: which level it rests under, the drop's low, and when the resting short is cancelled. */
  level_kind?: string;
  drop_low?: number;
  cancel_at?: number;
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
  /** ADR 042 draft: how many of the Five Pillars pass (absent on an older API). */
  pillars?: { passed: number; known: number; total: number } | null;
  /** Nova itself will take it: the bot, or Auto-entry on that stock (absent on an older API). */
  taken_by?: 'bot' | 'auto_entry' | null;
  /** Not a trade, with its reasons: still raised, never bought (absent on an older API). */
  not_a_trade?: { reasons: string[] } | null;
  /** ADR 049: a short proposal stages a short with its buy stop, never a buy (absent on an older API: long). */
  side?: SetupSide;
  ssr?: SsrState | null;
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
  /** A short's grade (ADR 049): the high of day over the prior close and the price under it, in percent. */
  run_pct?: number | null;
  fade_pct?: number | null;
  vwap?: number | null;
  /** Dilution on file and today's negative news; null when not read. */
  bad_news?: { dilution: boolean | null; negative: boolean | null; text: string | null } | null;
  /** IBKR's shortable estimate against the order's shares. */
  borrow?: { shares: number | null; state?: string | null; age_sec?: number | null; order_shares?: number | null } | null;
}

/** The 5-minute chart's read on a 1-minute setup (trial T8, backend `setup_scanner/five_minute.py`): the last
 *  complete 5-minute candle's close against the 9 EMA of 5-minute closes, and the 5-minute MACD histogram. */
export interface Tf5Read {
  agrees: boolean;
  above_ema9: boolean;
  macd_up: boolean;
  close: number;
  ema9: number;
  macd_hist: number;
  candles: number;
  /** The last complete 5-minute candle's start, epoch seconds. */
  as_of: number;
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
  /** Where the grade was read (2026-09-29): when the setup armed, or when its forming leg made its high. */
  graded?: 'armed' | 'forming' | null;
  /** Under a `filtered` row, where the pattern itself stands; null on every other row. */
  phase?: SetupState | null;
  tape: TapeRead | null;
  /** The tape gate's read at the trigger (null before one, and on a filtered setup). */
  trigger_tape?: { verdict: TapeVerdict; reasons: string[] } | null;
  proposal: SetupProposal | null;
  outcome: string | null;
  /** When the scoring's first touch (target 1 or the stop) printed. */
  outcome_at?: number | null;
  bar_r: number | null;
  mfe: number | null;
  mae: number | null;
  failed_at?: number | null;
  /** The 5-minute chart's read (trial T8), null while it has no complete candle; absent on an older API. */
  tf5?: Tf5Read | null;
  /** When it was read: at the trigger, when the setup armed, or when its forming leg made its high. */
  tf5_at?: 'trigger' | 'armed' | 'forming' | null;
  /** Too thin to trade? (2026-10-01) The armed setup's reading -- at its trigger once it triggered; null
   *  before it armed, on a filtered setup, and from an older API. */
  liquidity?: LiquidityRead | null;
  /** ADR 049: the side the row's setup trades (absent on an older API: long). */
  side?: SetupSide;
  /** A short row's SSR at its trigger, else at its arm; null on a long row. */
  ssr?: SsrState | null;
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
  /** ADR 042 draft: the setup's level under the master ceiling, min(master, own); absent on an older API. */
  effective?: number | null;
  /** Retired with the chosen setup (ADR 042 draft); an older API still sends it. */
  chosen?: boolean;
  proposing: boolean;
  template: { id: string; rev: number; name: string; params_hash?: string } | null;
  templates_watched: number;
  window: { start: string; end: string; state: 'before' | 'open' | 'after' | string };
  counts: SetupCounts;
  /** A recorded moment (`replay.kind` `journal`): false when Nova's eyes were not running this setup then. */
  recorded?: boolean;
  /** ADR 049: the side the setup trades (absent on an older API: long). */
  side?: SetupSide;
  /** A short setup's five-year test; null on a long one (absent on an older API). */
  test?: ShortTest | null;
}

/** Why a recorded moment has no board (backend `eyes/playback.py`). */
export interface SetupsRecordGap {
  reason: 'no_record' | 'before_record' | 'not_running' | string;
  since: number | null;
  until: number | null;
}

/** The Sim eyes' replay (ADR 029, ADR 052): what the board follows off the live edge -- a loaded Session
 *  Record (`capture`) or historical window (`history`) re-read by today's templates, or what Nova's live
 *  eyes recorded at the playhead (`journal`, operator ask 2026-09-24) when nothing is loaded. */
export interface SetupsReplay {
  kind: 'capture' | 'history' | 'journal' | string;
  date: string | null;
  symbol: string | null;
  playhead: number | null;
  at: number | null;
  loading: boolean;
  error: string | null;
  /** A stated absence: no record of that day, before it began, or a gap where Nova's eyes were off. */
  note: string | null;
  /** `journal`: what the Sim desk has loaded beside it (`historical` / `capture`), null when nothing. */
  loaded?: string | null;
  /** `history`: the window's source (`massive` / `ibkr`) and the book its tape gate reads (`nbbo` / `none`). */
  source?: string | null;
  book?: string | null;
  gap?: SetupsRecordGap | null;
  journal?: { path: string; exists: boolean; lines: number; folded: number; first_ts: number | null;
    last_ts: number | null; line_ts: number | null; skipped: number } | null;
}

export interface SetupsBoard {
  schema_version: number;
  generated_at: number;
  session_date: string | null;
  /** `live` (the market) or `sim` (off the live edge: the loaded Session Record, or the recorded eyes). */
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
