/** Wire shape of GET /api/practice/account (ADR 020 "Contract"). */
import type { IbkrOrder } from '../ibkr';
import type { PracticeVenue } from '../constantGroups/practice';
import type { Owner } from '../constantGroups/owners';

/** One holder of a position (ADR 072): you, Claude, the brain, or a retired bot (Earlier bots, by its origin). */
export interface PracticeOwnerHolding {
  owner: Owner;
  /** The retired bot, on Earlier bots' rows only. */
  bot: string | null;
  qty: number;
  avg_cost: number;
  unrealized_pnl: number;
  /** These shares are handed to you: a switched-off trader's, or a retired bot's. */
  handed?: boolean;
}

export interface PracticePosition {
  symbol: string;
  qty: number;
  avg_cost: number | null;
  mark: number | null;
  unrealized: number | null;
  /** Paper and Sim (ADR 072): every holder with shares. */
  by_owner?: PracticeOwnerHolding[];
}

/** One book's day (ADR 069, ADR 072). */
export interface PracticeBookDay {
  day_pnl: number;
  realized_today: number;
  unrealized_pnl: number;
  fills_today: number;
  commissions_today: number;
}

/** An AI trader's day and its budget (its limit, and what its open shares and working entries hold). */
export type PracticeTraderDay = PracticeBookDay & { budget_usd: number; budget_used_usd: number };

/** The account's four books (ADR 072); the four `day_pnl` add up to the account's. */
export interface PracticeBooks {
  you: PracticeBookDay;
  claude: PracticeTraderDay;
  brain: PracticeTraderDay;
  earlier_bots: PracticeBookDay & { by_bot: Record<string, PracticeBookDay> };
}

export interface PracticeAccount {
  venue: PracticeVenue;
  account_id: string;
  starting_cash: number;
  cash: number;
  buying_power: number;
  net_liquidation: number;
  gross_position_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  /** Open P&L at the price that closes each position now (long: bid, short: ask); null when a quote is missing. */
  unrealized_at_bid?: number | null;
  day_pnl: number;
  /** Realized P&L (net of fees) since the 04:00 ET practice-day boundary. */
  realized_today?: number | null;
  day_started_et: string | null;
  commissions_today: number;
  positions: PracticePosition[];
  /** Paper and Sim (ADR 072): the three traders' books and Earlier bots'. */
  books?: PracticeBooks;
  working: IbkrOrder[];
  fills_today: number;
  schema_version: number;
  updated_at: string | null;
  /** Sim only: which replay this scratch ledger belongs to. */
  /** Sim only: the ledger's replay binding, `[source, symbol, date, start?, end?]` (or a legacy string). */
  replay_key?: string | ReadonlyArray<string | number | null> | null;
}
