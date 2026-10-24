/**
 * `GET /api/bot/live-traders` and `/asks` (ADR 055) as the Live Trader panel reads them.
 * Shapes: architecture/schema/bot.md ("The Live Trader bot").
 */
export type LtSide = 'you' | 'nova';
export type LtMode = 'signal' | 'approve' | 'auto_entry' | 'bot';
export type LtTone = 'ok' | 'warn' | 'bad' | 'off' | 'plain';

export interface LtSettings {
  key: boolean;
  entry: LtSide;
  exit: LtSide;
  step_usd: number;
  adds: number | null;
  allowance_usd: number;
  sides: 'long' | 'both';
  short_stop_pct: number;
  take_open: boolean;
  /** Their size (2026-10-22): a copy order waits until the gap to their size is worth this; absent from an older
   * backend, which copied a full step per add. */
  lot_usd?: number;
  mode: LtMode;
  updated_at?: number | null;
}

export interface LtPosition {
  id: string;
  row_id: string;
  symbol: string;
  side: 'long' | 'short';
  qty: number;
  avg_cost: number | null;
  their_avg: number | null;
  now: number | null;
  pl_usd: number | null;
  steps: number;
  adds_followed: number;
  opened_ts: number;
  state: 'entering' | 'open' | 'closing';
  order_id: number | null;
  note: string | null;
}

export interface LtAsk {
  id: string;
  host?: string;
  row_id: string;
  symbol: string;
  side: 'long' | 'short';
  step: 'entry' | 'already_open' | 'add';
  their_price: number | null;
  qty: number;
  limit: number;
  stop: number | null;
  created_ts: number;
  expires_ts: number;
  text: string;
  approved: boolean;
  answered: boolean | null;
  seconds_left: number;
}

export interface LtEvent {
  ts: number | null;
  tone: LtTone;
  outcome: string;
  symbol: string | null;
  text: string | null;
  code: string | null;
  late_sec: number | null;
}

export interface LtHost {
  name: string;
  face: string | null;
  on_air: boolean | null;
  left_ts: number | null;
  settings: LtSettings;
  state: { tone: LtTone; text: string };
  allowance: { used_usd: number; of_usd: number };
  /** ``pl_usd`` is before fees. The fee fields are absent from a backend older than 2026-10-19: the strip then
   *  shows ``pl_usd`` alone, as it did. */
  today: { pl_usd: number; realized_usd: number; unrealized_usd: number; trades: number; skipped: number;
    series: [number | null, number][]; net_pl_usd?: number; fees_usd?: number; orders?: number; fees_unread?: number };
  positions: LtPosition[];
  asks: LtAsk[];
  events: LtEvent[];
}

export interface LiveTradersView {
  schema_version: number;
  generated_at: number;
  enabled: boolean;
  venue: 'paper';
  desk_venue: string | null;
  can_trade: { ok: boolean; code: string | null; why: string | null };
  sell_all_at: string;
  sell_all_ts: number | null;
  watcher: { running: boolean; pass_ts: number | null; idle: boolean;
    feed: { state: string | null; error: string | null; read_age_sec: number | null; behind_sec: number | null;
      bar_visible: boolean | null; live: boolean | null };
    text: string };
  settings_error: string | null;
  book_error: string | null;
  hosts: LtHost[];
  defaults: Partial<LtSettings>;
  bounds: Record<string, unknown>;
}

export interface LtHeld {
  host: string;
  symbol: string;
  side: 'long' | 'short';
  qty: number;
  state: string;
}

export interface LiveTraderAsksView {
  schema_version: number;
  generated_at: number;
  asks: LtAsk[];
  held: LtHeld[];
}

export type LtPatch = Partial<Omit<LtSettings, 'mode' | 'updated_at'>>;
