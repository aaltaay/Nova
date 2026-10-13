/** `GET /api/why/{symbol}` (ADR 028; AGENTS.md §3 "Why it's moving"): a rules read of what drove a mover.
 * `GET /api/why?symbols=...&board=...` answers the same read for many symbols (the Catalyst column). */
import type { CatalystVerdict } from './catalystVerdict';

export type WhyCheckState = 'yes' | 'no' | 'unknown';

export interface WhyCheck {
  /** news | halts | float | float_rotation | reverse_split | short_interest | borrow | volume */
  id: string;
  label: string;
  state: WhyCheckState;
  value: string | null;
  detail: string | null;
  source: string;
  /** Epoch seconds the fact is as of, when known. */
  as_of: number | null;
}

/** One rung of the ladder (`likely.steps`, rules v5): a cause in the rules' order, whether it fits, and why. */
export interface WhyStep {
  /** move (the move itself, first) | news_pending | news | short_squeeze | routine_news | split_squeeze |
   * low_float_momentum | thin_trading | unexplained */
  kind: string;
  name: string;
  /** null: a fact it needs is unknown. */
  fits: boolean | null;
  why: string;
}

export interface WhyLikely {
  /** not_moving | news_pending | news | short_squeeze | routine_news | split_squeeze | low_float_momentum | thin_trading | unexplained,
   * or not_read (a Sim replay no record reaches: no checks, the reason in `detail`) */
  kind: string;
  label: string;
  detail: string | null;
  /** `possible` when a deciding fact is unknown. */
  confidence: 'likely' | 'possible';
  /** The ladder behind it (empty from an API before rules v5, and on `not_read`). */
  steps?: WhyStep[];
}

/** Which price a read used (backend `MOVE_PRICED_BY_*`). */
export type WhyPricedBy = 'board_row' | 'last_trade' | 'row' | 'quote' | 'replay';

/** The few facts the Catalyst hover names beside the checks. */
export interface WhyReadFacts {
  /** The board whose row was read (gappers | gainers | losers | afterhours | large_cap), else null. */
  board: string | null;
  priced_by: WhyPricedBy | null;
  price: number | null;
  change_pct: number | null;
  /** The L1 line's last trade when the read took a board's own price instead. */
  last_trade: { price: number; change_pct: number | null; ts: number } | null;
  /** The news verdict the read used: its headline, source and time. */
  catalyst: CatalystVerdict | null;
}

export interface WhyMovingRead {
  schema_version: number;
  symbol: string;
  /** Epoch seconds the read is as of: now, or on a Sim replay the playhead. */
  generated_at: number;
  rules_version: string;
  /** A Sim replay desk: the replayed day's facts as of the playhead (`generated_at`), none after it. */
  replay?: boolean;
  likely: WhyLikely;
  checks: WhyCheck[];
  /** Always set by `normalizeWhyMoving`. */
  facts?: WhyReadFacts;
}

/** `GET /api/why?symbols=...&board=...`: each symbol's read; a failed one is null with its error. */
export interface WhyBatch {
  board: string | null;
  replay: boolean;
  generated_at: number;
  reads: Record<string, WhyMovingRead | null>;
  errors: Record<string, string>;
}
