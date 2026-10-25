/** The Market page's wire (ADR 053; architecture/schema/market-board.md). Percent points, epoch seconds. */

export type Period = '1D' | '7D' | '30D';
export type TopKind = 'biggest' | 'runners';
export type CheckState = 'green' | 'amber' | 'red' | 'waiting' | 'unknown';

export interface Session {
  date: string;
  phase: 'premarket' | 'regular' | 'after_hours' | 'closed';
  open_at: number;
  close_at: number;
  next: { kind: 'premarket' | 'open' | 'close' | 'after_hours_end'; at: number } | null;
  holiday: string | null;
}

export interface Check {
  id: 'futures' | 'breadth' | 'vix' | 'small_caps' | 'runners' | 'gappers';
  label: string;
  state: CheckState;
  value: number | null;
  text: string;
  starts_at: number | null;
  why: string | null;
}

/** The small-cap temperature (ADR 053 amendment 2026-10-25): a day or a month is hot / warm / cold, a week good /
 * ok / choppy / cold. */
export type DayTemp = 'hot' | 'warm' | 'cold';
export type WeekTemp = 'good' | 'ok' | 'choppy' | 'cold';
export type TempLabel = DayTemp | WeekTemp;

export interface DayRead {
  verdict: 'bullish' | 'mixed' | 'bearish' | null;
  green: number;
  red: number;
  known: number;
  total: number;
  checks: Check[];
  /** Today, the last 5 and the last 21 sessions; never part of the verdict. Absent on an API from before
   * 2026-10-25, `null` until the climate has answered. */
  temperature?: { day: DayTemp | null; week: WeekTemp | null; month: DayTemp | null } | null;
}

export interface MarketEvent {
  at: number;
  kind: 'econ' | 'fomc' | 'earnings' | 'holiday';
  title: string;
  detail: string | null;
  source: string;
}

export interface Events {
  items: MarketEvent[];
  bond_market: { closed: boolean; early_close_at: number | null; why: string | null };
}

export interface QuoteTile {
  id: string;
  label: string;
  symbol: string;
  kind: 'future' | 'index' | 'crypto' | 'spread';
  exchange: string;
  contract: string | null;
  last: number | null;
  prev_close: number | null;
  change: number | null;
  change_pct: number | null;
  price_basis: 'last' | 'mid' | 'bars' | null;
  data_type: 'live' | 'frozen' | 'delayed' | 'delayed_frozen' | 'bars' | null;
  at: number | null;
  /** `last` came from a bar older than the backend's freshness window (the market is not trading). Absent on a
   * backend from before ADR 053's 2026-10-13 evening amendment. */
  stale?: boolean;
  line: [number, number][];
  error: string | null;
}

export interface BreadthNumbers {
  advancing: number | null;
  declining: number | null;
  up_volume: number | null;
  down_volume: number | null;
  tick: number | null;
  trin: number | null;
}

export interface Breadth extends BreadthNumbers {
  state: 'ok' | 'waiting' | 'unavailable';
  why: string | null;
  at: number | null;
  data_type: string | null;
  unchanged: number | null;
  ad_line: [number, number][];
  line_since: number | null;
  prior: (BreadthNumbers & { date: string }) | null;
}

export interface BoardRow {
  name: string;
  etf: string;
  change_pct: number | null;
  context_pct: number | null;
  context_period: Period;
  leader: { symbol: string; change_pct: number } | null;
  leader_why: string | null;
}

export interface SectorBoard {
  period: Period;
  from: string;
  to: string;
  rows: BoardRow[];
  offense_pct?: number | null;
  defense_pct?: number | null;
}

export interface ClimateCounts {
  up20: number | null;
  up50: number | null;
  up100: number | null;
}

/** One session's temperature inputs; `null` numbers when Nova recorded no Gainers board that session. */
export interface HeatDay {
  date: string;
  label: DayTemp | null;
  runners_100: number | null;
  /** Shares x last price of the five biggest gainers ($2-20 prior close), dollars. */
  money: number | null;
  usual_money: number | null;
  usual_days: number;
  hold_pct: number | null;
}

export interface Heat {
  label: TempLabel | null;
  why: string | null;
  price_min: number;
  price_max: number;
  days: HeatDay[];
  hot: number;
  warm: number;
  cold: number;
  labelled: number;
  hold_pct: number | null;
  score_pct: number | null;
}

export interface Climate {
  period: Period;
  from: string;
  to: string;
  sessions: number;
  covered: number;
  lens: { board: string; rank_max: number; price_min: number };
  counts: ClimateCounts;
  per_day: number | null;
  baseline: (ClimateCounts & { per_day: number; days: number; basis: 'same_minute' | 'per_session' }) | null;
  temperature: TempLabel | null;
  /** The temperature's inputs; absent on an API from before 2026-10-25. */
  heat?: Heat | null;
  days: { date: string; source: string | null; total: number | null; themes: Record<string, number> }[];
  theme: { name: string; count: number; total: number; share_pct: number | null; prev_share_pct: number | null } | null;
  themes: { name: string; count: number; prev_count: number }[];
  gappers: { held: number; total: number; gone: number; rate_pct: number | null; baseline_rate_pct: number | null };
  halts: { count: number; last: { symbol: string; at: number } | null; by_side: null; by_side_why: string };
  top: {
    symbol: string;
    change_pct: number;
    date: string;
    price: number | null;
    float_shares: number | null;
    theme: string;
    news_at: number | null;
  }[];
}

export interface TopRow {
  symbol: string;
  last: number | null;
  change_pct: number | null;
  spark: number[] | null;
}

export interface TopCard {
  name: string;
  etf: string | null;
  change_pct: number | null;
  rows: TopRow[];
}

export interface TopStocks {
  kind: TopKind;
  period: Period;
  cards: TopCard[];
  why: string | null;
}

export interface SourceStatus {
  id: string;
  label: string;
  ok: boolean | null;
  at: number | null;
  error: string | null;
}

export interface MarketBoard {
  schema_version: number;
  generated_at: number;
  enabled: boolean;
  loading: boolean;
  replay_desk: boolean;
  session: Session;
  day_read: DayRead;
  events: Events;
  quotes: QuoteTile[];
  breadth: Breadth;
  sectors: SectorBoard;
  industries: SectorBoard;
  climate: Climate | null;
  top: TopStocks;
  sources: SourceStatus[];
}

/** Each block's switch, remembered on the desk (periods.ts). */
export interface BlockPeriods {
  sectors: Period;
  industries: Period;
  climate: Period;
  top: { kind: TopKind; period: Period };
}
