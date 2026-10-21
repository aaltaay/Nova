/** The Forex page's wire (ADR 061; architecture/schema/forex-board.md). Percent points, epoch seconds, US dollars. */

export type Period = '1D' | '7D' | '30D';
/** What the map and Follow the sun show (the switch). */
export type ColorBy = 'strength' | 'futures';
export type Verdict = 'safe_havens' | 'risk_on' | 'dollar_bought' | 'dollar_sold' | 'quiet';
export type SessionId = 'asia' | 'london' | 'new_york';

export interface Instrument {
  kind: 'spot' | 'future';
  symbol: string;
  label: string;
  exchange: string;
  currency: string;
  contract: string | null;
  multiplier: number | null;
}

export interface FxDay {
  from: number;
  to: number;
  open: boolean;
  next_open_at: number | null;
}

export interface Market {
  total_usd: number;
  exchange_traded_usd: number;
  covered_pct: number;
  instruments: { name: string; usd: number }[];
  desks: { name: string; usd: number; share_pct: number }[];
  regions: { asia_pacific: number; europe: number; americas: number };
  as_of: string;
  source: string;
  url: string;
}

export interface Read {
  verdict: Verdict | null;
  headline: string;
  detail: string;
  rose: string[];
  fell: string[];
  rule: string;
}

export interface Dollar {
  strength_pct: number | null;
  priced: number;
  up_against: number;
  down_against: number;
  pressure_usd: number | null;
  pressure_pct: number | null;
  traded_usd: number | null;
  size_usd: number;
  share_pct: number;
}

export interface Session {
  id: SessionId;
  name: string;
  from: number;
  to: number;
  state: 'done' | 'now' | 'later';
  rose: { code: string; pct: number } | null;
  fell: { code: string; pct: number } | null;
  desks: { label: string; share_pct: number };
}

export interface Home {
  open: boolean;
  open_at: number | null;
  close_at: number | null;
  next_open_at: number | null;
}

export interface Size {
  usd: number;
  share_pct: number;
  rank: number;
  pair: string;
  pair_usd: number;
}

export interface Price {
  basis: 'spot' | 'future' | null;
  instrument: Instrument | null;
  pair: string | null;
  rate: number | null;
  open: number | null;
  pair_pct: number | null;
  vs_usd_pct: number | null;
  at: number | null;
  data_type: string | null;
  error: string | null;
}

export interface Refusal {
  instrument: string | null;
  error: string | null;
}

export interface Futures {
  basis: 'future' | 'sum' | null;
  instrument: Instrument | null;
  inverted: boolean | null;
  traded_usd: number | null;
  up_usd: number | null;
  down_usd: number | null;
  pressure_usd: number | null;
  pressure_pct: number | null;
  contracts: number | null;
  last_bar_at: number | null;
  at: number | null;
  error: string | null;
  refused: Refusal[];
}

export interface Currency {
  code: string;
  name: string;
  city: string;
  lat: number;
  lon: number;
  tz: string;
  home: Home;
  size: Size;
  price: Price;
  strength_pct: number | null;
  by_session: Record<SessionId, number | null> | null;
  range_x: number | null;
  volume_x: number | null;
  futures: Futures;
  mixed: boolean;
}

export interface SunHour {
  t: number;
  strength: Record<string, number>;
  futures: Record<string, number>;
}

export interface Sun {
  from: number;
  to: number;
  now: number;
  hours: SunHour[];
  tracks: { id: SessionId; name: string; from: number; to: number; share_pct: number }[];
}

export interface SourceStatus {
  id: string;
  label: string;
  ok: boolean | null;
  at: number | null;
  error: string | null;
}

/** Why the reads wait: IBKR's history requests left in its 10 minutes, and the number Forex reads above. */
export interface Budget {
  history_left: number | null;
  history_headroom: number;
  waiting: 'history' | 'lines' | null;
}

export interface ForexBoard {
  schema_version: number;
  generated_at: number;
  enabled: boolean;
  loading: boolean;
  replay_desk: boolean;
  period: Period;
  fx_day: FxDay;
  market: Market;
  read: Read;
  dollar: Dollar;
  sessions: Session[];
  currencies: Currency[];
  sun: Sun;
  sources: SourceStatus[];
  budget: Budget;
}
