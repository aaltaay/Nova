/** The brain as `GET /api/traders` answers it (ADR 072, `architecture/schema/traders.md` "On the wire"). */

export type BrainState = 'off' | 'watching' | 'buy_set' | 'in_trade' | 'done';

/** Lane 3: the one stock the brain named, and whether its lines are up. */
export interface BrainSeatLane {
  symbol: string | null;
  depth: boolean;
  tape: boolean;
  /** The brain's own words for naming the stock. */
  why: string | null;
}

export interface BrainPosition {
  symbol: string;
  qty: number;
  avg_cost: number | null;
  mark: number | null;
  unrealized_pnl: number | null;
}

/** A position the brain's switch handed to you: yours to close, its stop still resting. */
export interface BrainHanded {
  symbol: string;
  qty: number;
  stop_price: number | null;
}

/** One thing the brain is reading now: on its own lane (Level 2), or on Level 1. */
export interface BrainReading {
  symbol: string;
  text: string;
  source: 'lane' | 'level1';
}

export interface BrainEvent {
  at: number;
  kind: string;
  symbol: string | null;
  text: string;
}

export interface BrainSeatStatus {
  /** The desk's venue as the payload names it (`paper`, `sim`, `live`); null when it names none. */
  venue: string | null;
  on: boolean;
  /** When the switch last flipped (epoch seconds), or null. */
  at: number | null;
  can_turn_on: boolean;
  /** Why On would be refused now, in Nova's words; null while it would not be. */
  why_not_on: { reason: string; error: string } | null;
  done_for_today: boolean;
  state: BrainState;
  /** The pill's words as the backend writes them. */
  text: string;
  symbol: string | null;
  lane: BrainSeatLane;
  position: BrainPosition | null;
  handed: BrainHanded[];
  today: { pnl: number | null; loss_limit_usd: number | null; tripped_at: number | null };
  limits: {
    max_shares: number | null; risk_usd: number | null; budget_usd: number | null; budget_used_usd: number | null;
    flat_by: string | null;
  };
  note: { text: string; at: number } | null;
  /** The brain's program checked in lately; null on a backend that does not say (from before the brain's door). */
  connected: boolean | null;
  reading: BrainReading[];
  /** Newest first. */
  events: BrainEvent[];
  /** The payload's own `error` (the switches file could not be read), in Nova's words. */
  read_error: string | null;
  generated_at: number;
}
