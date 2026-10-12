/** The bot's read on one stock (ADR 036): the wire shapes of `/api/stock-read/{symbol}` and its
 * decisions / history reads (AGENTS.md §3, "The bot's read on one stock"). Who trades the stock's own endpoint
 * (ADR 037) has its shapes in `stockModeTypes.ts`, re-exported here. */

import type { LiquidityRead, SetupTargets, TargetFields } from '../setups';
import type { StockHeld } from './heldRead';
import type { LevelMap, PlanLevels } from './levelTypes';

export type {
  StockModeApproval,
  StockModeBot,
  StockModeEntries,
  StockModeHalf,
  StockModeName,
  StockModeNote,
  StockModeSize,
  StockModeTrade,
  StockModeView,
  StockSide,
} from './stockModeTypes';

export type ReadState = 'ok' | 'warn' | 'bad' | 'unknown' | 'info';

export type ReadGroupId = 'in_play' | 'setups' | 'front' | 'tape' | 'short' | 'float' | 'halts';

export interface ReadRow {
  id: string;
  label: string;
  value: string;
  detail: string | null;
  state: ReadState;
  source: string;
  as_of: number | null;
}

export interface ReadGroup {
  id: ReadGroupId;
  label: string;
  question: string;
  verdict: ReadState;
  value: string;
  rows: ReadRow[];
}

export interface PlanCheck {
  id: string;
  state: ReadState;
  text: string;
}

export interface PlanMark {
  price: number;
  label: string;
  kind: 'hod' | 'vwap' | 'pmh' | 'round' | 'wall' | 'open';
  size: number | null;
  /** The target it stands before (#845): 1, or 2 past target 1; absent from an older backend. */
  before?: 1 | 2;
}

export interface TapeVerdict {
  verdict: string;
  reasons: string[];
}

export interface SetupWindow {
  start: string;
  end: string;
  state: string;
}

/** How many of the Five Pillars pass and how many are known (2026-09-29). */
export interface PlanPillars {
  passed: number;
  known: number;
  total: number;
}

/** A setup plan is a trade, or not and why (2026-09-29); null for the operator's own plan. */
export interface PlanTrade {
  ok: boolean;
  reasons: string[];
}

/** A triggered setup's first touch once it printed. */
export interface PlanResult {
  outcome: 'target_first' | 'stop_first';
  at: number | null;
  r: number | null;
  text: string;
}

export interface StockPlan {
  source: 'setup' | 'manual';
  /** ADR 048: a short plan sells at its entry, protects with a buy stop over it and covers under it. Absent
   * (a backend before it, a fixture): long. */
  side?: 'long' | 'short';
  setup_type: string | null;
  /** The live setup the plan follows (null for a forming setup or the operator's own plan): what an
   * approval binds to (ADR 037). */
  setup_id: string | null;
  kind: string | null;
  state: 'forming' | 'armed' | 'near' | 'triggered' | 'manual';
  provisional: boolean;
  trigger: number | null;
  entry: number | null;
  stop: number | null;
  /** Target 1 (#845): the first part's sell, from the strategy's target menu. */
  target: number | null;
  /** Target 2: the rest's sell; null when everything sells at target 1. Absent (a fixture, an older backend): none. */
  target2?: number | null;
  /** The share sold at target 1 (0.5 with a target 2, 1 without); null when the wire does not state it. */
  target1_fraction?: number | null;
  /** Each target's kind, price and the words it came from ("1c under $4.50"); null from an older backend. */
  targets?: SetupTargets | null;
  risk: number | null;
  reward: number | null;
  /** Target 1 in R -- the risk a share is the unit results are measured in, never a target rule. */
  rr: number | null;
  reward2?: number | null;
  /** Target 2 in R; null without a target 2. */
  rr2?: number | null;
  /** The strategy's target menu in words ("target 1: 20c, or 1c before a half / whole dollar ...; 50% at target 1"). */
  target_rule: string;
  entry_rule: string;
  stop_rule: string;
  grade: string | null;
  pillars: PlanPillars | null;
  trade: PlanTrade | null;
  result: PlanResult | null;
  reason: string;
  tape: TapeVerdict | null;
  flow: { score: number | null; label: string } | null;
  window: SetupWindow | null;
  checks: PlanCheck[];
  marks: PlanMark[];
  /** Null from a backend older than the level map, or with no map to read. */
  levels: PlanLevels | null;
  /** Too thin to trade? (2026-10-01) The stock now, the book walked for the plan's size; absent from an older
   *  backend. A thin setup plan is not a trade, and the chart draws no plan for it. */
  liquidity?: LiquidityRead | null;
}

/** An armed (or triggered) setup's levels; target 2 and the split ride beside target 1 (`TargetFields`, #845). */
export interface SetupLevels extends TargetFields {
  trigger: number;
  entry: number;
  stop: number;
  risk: number;
  target1: number;
  leg_t?: number;
  leg_high?: number;
  leg_low?: number;
  pullback_bars?: number;
  armed_bar_t?: number;
  triggered_at?: number;
  trigger_price?: number;
  detail?: Record<string, unknown> | null;
}

export interface FormingLevels extends TargetFields {
  trigger: number;
  entry: number;
  stop: number;
  risk: number;
  target1: number;
  bars: number;
  blocked: string | null;
  waiting: string | null;
}

export interface SetupLeg {
  t: number;
  high: number;
  low: number;
  pct: number;
  bars?: number;
  /** A flat top's touches, `[time, high]` oldest first, and the zone a high reached to touch it (2026-10-06). */
  touches?: [number, number][];
  zone?: number;
}

export interface LaneSeries {
  bars_as_of: number;
  close: number;
  ema: number;
  macd_line: number;
  macd_signal: number;
  macd_hist: number;
  hod: number;
}

export interface SetupLane {
  setup_type: string;
  state: string;
  reason: string;
  kind: string | null;
  chosen: boolean;
  level: number;
  setup: SetupLevels | null;
  forming: FormingLevels | null;
  leg: SetupLeg | null;
  last_price: number | null;
  distance: number | null;
  grade: string | null;
  /** Under a `filtered` lane, where the pattern itself stands (2026-09-29). */
  phase: string | null;
  tape: TapeVerdict | null;
  window: SetupWindow | null;
  series: LaneSeries | null;
  /** The lane's candles (2026-09-30): the setups in play read 1-minute ones; the built-in 5-minute lanes
   *  (`setups_5m`) read 5-minute ones and draw only on the 5-minute chart. */
  timeframe?: '1m' | '5m';
  /** Too thin to trade? (2026-10-01) The armed setup's reading, at its trigger once it triggered. */
  liquidity?: LiquidityRead | null;
  /** ADR 049: a short setup sells at its entry and covers under it (absent on an older API: long). */
  side?: 'long' | 'short';
  /** A short lane's SSR at its trigger, else at its arm; null on a long one (absent on an older API). */
  ssr?: 'on' | 'off' | 'unknown' | null;
}

export interface ReadLevels {
  hod: { price: number; ts: number } | null;
  pmh: number | null;
  open: number | null;
  prev_close: number | null;
  vwap: number | null;
  round_above: number | null;
  round_below: number | null;
}

export interface StockRead {
  schema_version: number;
  symbol: string;
  generated_at: number;
  session_date: string;
  price: number | null;
  prev_close: number | null;
  change_pct: number | null;
  followed: boolean;
  followed_note: string | null;
  replay: boolean;   // a Sim replay's read at the playhead (ADR 052): the Sim eyes' lanes, the replay's candles
  setups: SetupLane[];
  /** The 5-minute lanes (first pullback, bull flag, flat top on 5-minute candles): chart only, never a plan. */
  setups_5m: SetupLane[];
  no_scanner: { setup_type: string; label: string; reason: string }[];
  plan: StockPlan | null;
  /** The trade you hold, measured from the price (ADR 036 amendment 2026-10-01); null when nothing is held. */
  held: StockHeld | null;
  levels: ReadLevels;
  /** Null from a backend older than the level map. */
  level_map: LevelMap | null;
  groups: ReadGroup[];
  counts: Record<ReadState, number>;
}

export interface DecisionEvent {
  ts: number;
  lane: string;
  event: string;
  title: string;
  detail: string | null;
  count: number;
  last_ts: number | null;
  /** The leg or the armed setup the journal line carried, to draw at `ts`. */
  levels: { leg: SetupLeg | null; setup: SetupLevels | null } | null;
}

export interface StockDecisions {
  symbol: string;
  date: string;
  summary: {
    text: string;
    legs: number;
    armed: number;
    near: number;
    triggered: number;
    trades: number;
    refusals: { reason: string; count: number }[];
  };
  events: DecisionEvent[];
  sources: Record<string, { ok: boolean; error: string | null }>;
}

export interface DailyBar {
  d: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface RunDay {
  date: string;
  prior_close: number;
  high: number;
  close: number;
  run_pct: number;
  close_pct: number;
  today: boolean;
}

/** Yahoo's last split: `factor` "1:10" is a 1-for-10 reverse split. */
export interface SplitFact {
  factor: string | null;
  ts: number | null;
  reverse: boolean | null;
  days_ago: number | null;
}

export interface StockHistory {
  symbol: string;
  daily: DailyBar[];
  runs: RunDay[];
  split: SplitFact | null;
  holdings: ReadRow[];
}

