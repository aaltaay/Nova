/** `GET /api/agent/trader` (ADR 068, `architecture/schema/agent-trader.md`): what the desk shows of Claude. */

export type ClaudeSeatState =
  | 'off' | 'idle' | 'waiting_line' | 'watching' | 'buy_set' | 'in_trade' | 'yielded' | 'done';

export interface ClaudeOrder {
  order_id: number;
  symbol: string;
  side: string;
  order_type: string | null;
  qty: number;
  limit_price: number | null;
  stop_price: number | null;
  /** A bracket's role: the entry (`parent`), a target, the stop; null for a plain order. */
  leg_role: 'parent' | 'target' | 'target2' | 'stop' | null;
  status: string | null;
  parent_id: number | null;
}

export interface ClaudeBreak {
  id: string;
  symbol: string;
  qty: number;
  trigger: number;
  top: number;
  stop: number;
  target: number;
  target2: number | null;
  target1_qty: number | null;
  expires_at: number;
  created_at: number;
  why: string | null;
}

export interface ClaudeReflex {
  id: string;
  symbol: string;
  kind: string;
  action: string;
  why: string | null;
  /** The reflex in plain words, as the panel lists it. */
  text: string;
  expires_at: number | null;
}

export interface ClaudeEvent {
  at: number;
  kind: string;
  text: string;
}

export interface ClaudeLine {
  symbol: string | null;
  depth: boolean;
  tape: boolean;
  why_not: string | null;
  desk_lines: string[];
  desk_cap: number | null;
  all_lines: string[];
  /** The hidden Trader tab whose line Claude holds (ADR 068 decision 14); null when none lent it. */
  from_tab: string | null;
  /** Tabs the operator took back from Claude: never taken again while they are open. */
  taken_back: string[];
}

export interface ClaudeSeatStatus {
  state: ClaudeSeatState;
  text: string;
  on: boolean;
  since: number | null;
  beat_at: number | null;
  lease_until: number | null;
  lapsed: boolean;
  yielded: boolean;
  symbol: string | null;
  line: ClaudeLine;
  positions: { symbol: string; qty: number; mark: number | null }[];
  working: ClaudeOrder[];
  breaks: ClaudeBreak[];
  reflexes: ClaudeReflex[];
  today: { entries: number; max_entries: number | null; pnl: number | null; day_stop: number | null; fills: number };
  limits: { max_shares: number | null; max_risk_usd: number | null };
  note: { text: string; at: number } | null;
  /** Newest first. */
  events: ClaudeEvent[];
  read_error: string | null;
  generated_at: number;
}
