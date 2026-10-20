/** The Global page's wire (ADR 060; architecture/schema/global-board.md). Percent points, epoch seconds, US dollars. */

export type Period = '1D' | '7D' | '30D';
export type RegionId = 'americas' | 'europe' | 'middle_east_africa' | 'asia_pacific';
export type Basis = 'index' | 'future' | 'etf';
export type SessionState = 'open' | 'break' | 'closed' | 'holiday';
export type Verdict = 'money_in' | 'money_out' | 'rotation' | 'quiet';
/** What the map's colour shows (the switch). */
export type ColorBy = 'pressure' | 'move';

export interface Instrument {
  kind: Basis;
  symbol: string;
  label: string;
  exchange: string;
  currency: string;
  contract: string | null;
  multiplier: number | null;
}

export interface MarketSession {
  date: string | null;
  state: SessionState;
  open_at: number | null;
  close_at: number | null;
  segments: [number, number][];
  next_open_at: number | null;
  calendar: 'nyse' | 'clock';
}

export interface Move {
  basis: Basis | null;
  instrument: Instrument | null;
  pct: number | null;
  last: number | null;
  prev_close: number | null;
  at: number | null;
  data_type: string | null;
  error: string | null;
}

export interface Refusal {
  instrument: string | null;
  error: string | null;
}

export interface Flow {
  basis: Basis | null;
  instrument: Instrument | null;
  from: number | string | null;
  to: number | string | null;
  bars: number | null;
  sessions: number | null;
  up_usd: number | null;
  down_usd: number | null;
  flat_usd: number | null;
  traded_usd: number | null;
  pressure_usd: number | null;
  pressure_pct: number | null;
  last_bar_at: number | null;
  fx: { currency: string; usd_per_unit: number; date: string | null } | null;
  at: number | null;
  error: string | null;
  refused: Refusal[];
}

export interface Market {
  id: string;
  name: string;
  exchange: string;
  city: string;
  region: RegionId;
  lat: number;
  lon: number;
  tz: string;
  session: MarketSession;
  move: Move;
  flow: Flow;
  mixed: boolean;
}

export interface Totals {
  pressure_usd: number | null;
  traded_usd: number | null;
  pressure_pct: number | null;
  markets: number;
  flows: number;
  up: number;
  down: number;
  avg_move_pct: number | null;
}

export interface Region extends Totals {
  id: RegionId;
  label: string;
}

export interface Read {
  verdict: Verdict | null;
  headline: string;
  detail: string;
  rule: string;
}

export interface SunHour {
  t: number;
  net_usd: number;
  traded_usd: number;
  markets: number;
  by_region: Partial<Record<RegionId, number>>;
}

export interface Sun {
  from: number;
  to: number;
  now: number;
  hours: SunHour[];
  sessions: { market: string; region: RegionId; start: number; end: number }[];
}

export interface SourceStatus {
  id: string;
  label: string;
  ok: boolean | null;
  at: number | null;
  error: string | null;
}

export interface GlobalBoard {
  schema_version: number;
  generated_at: number;
  enabled: boolean;
  loading: boolean;
  replay_desk: boolean;
  period: Period;
  read: Read;
  world: Totals;
  regions: Region[];
  markets: Market[];
  sun: Sun;
  sources: SourceStatus[];
  budget: Budget;
}

/** Why the reads wait: IBKR's history requests left in its 10 minutes, and the number Global reads above. */
export interface Budget {
  history_left: number | null;
  history_headroom: number;
  waiting: 'history' | 'lines' | null;
}
