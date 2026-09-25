/** The bot's read on one stock (ADR 036): the wire shapes of `/api/stock-read/{symbol}` and its
 * decisions / history reads (AGENTS.md §3, "The bot's read on one stock"). */

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

export interface StockPlan {
  source: 'setup' | 'manual';
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
  target: number | null;
  risk: number | null;
  reward: number | null;
  rr: number | null;
  target_rule: string;
  entry_rule: string;
  stop_rule: string;
  grade: string | null;
  reason: string;
  tape: TapeVerdict | null;
  flow: { score: number | null; label: string } | null;
  window: SetupWindow | null;
  checks: PlanCheck[];
  marks: PlanMark[];
}

export interface SetupLevels {
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

export interface FormingLevels {
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
  tape: TapeVerdict | null;
  window: SetupWindow | null;
  series: LaneSeries | null;
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
  setups: SetupLane[];
  no_scanner: { setup_type: string; label: string; reason: string }[];
  plan: StockPlan | null;
  levels: ReadLevels;
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

/** Who trades the stock (ADR 037): `GET /api/stock-mode/{symbol}` (AGENTS.md §3, "Who trades the stock"). */
export type StockModeName = 'signal' | 'approve' | 'auto_entry' | 'bot';
export type StockSide = 'you' | 'nova';

export interface StockModeApproval {
  setup_id: string;
  setup_type: string | null;
  entry: number;
  stop: number;
  target: number;
  qty: number;
  approved_at: number;
  state: 'waiting' | 'sent' | 'withdrawn';
  reason: string | null;
}

export interface StockModeTrade {
  kind: 'auto_entry' | 'approve' | 'bot';
  state: 'entering' | 'holding' | 'closed' | 'missed' | 'handed';
  venue: string | null;
  venue_day: string | null;
  setup_id: string | null;
  setup_type: string | null;
  qty: number | null;
  entry: number | null;
  stop: number | null;
  target: number | null;
  entry_order_id: number | null;
  target_order_id: number | null;
  stop_order_id: number | null;
  fill_price: number | null;
  filled_at: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  /** Who sells it: Nova holds the exits (Approve's bracket, the bot), or the operator does. */
  exits: StockSide;
  sent_at: number | null;
  closed_at: number | null;
  note: string | null;
  /** The bot is selling it now. */
  exiting: boolean;
}

export interface StockModeNote {
  id: string;
  tone: 'info' | 'warn';
  text: string;
}

export interface StockModeView {
  symbol: string;
  generated_at: number;
  venue: 'live' | 'paper' | 'sim' | null;
  mode: StockModeName;
  buy: StockSide;
  sell: StockSide;
  risk_usd: number | null;
  set_at: number | null;
  /** Why Nova cannot take each side now; null: it can. */
  locks: { buy: string | null; sell: string | null };
  notes: StockModeNote[];
  approval: StockModeApproval | null;
  trade: StockModeTrade | null;
  nova_entries_today: number;
  last_event: { ts: number; tone: 'info' | 'ok' | 'warn' | 'bad'; text: string } | null;
  bot: { on_list: boolean; playing: boolean; reason: string | null; setup: string | null } | null;
}
