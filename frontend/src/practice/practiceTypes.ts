/** Wire shape of GET /api/practice/account (ADR 020 "Contract"). */
import type { IbkrOrder } from '../ibkr';
import type { PracticeVenue } from '../constantGroups/practice';

/** One holder of a Paper position (ADR 069): yours, or a bot's (by its origin). */
export interface PracticeOwnerHolding {
  owner: 'you' | 'bots';
  bot: string | null;
  qty: number;
  avg_cost: number;
  unrealized_pnl: number;
}

export interface PracticePosition {
  symbol: string;
  qty: number;
  avg_cost: number | null;
  mark: number | null;
  unrealized: number | null;
  /** Paper (ADR 069): every holder with shares; absent on Sim. */
  by_owner?: PracticeOwnerHolding[];
}

/** One book's day (ADR 069). */
export interface PracticeBookDay {
  day_pnl: number;
  realized_today: number;
  unrealized_pnl: number;
  fills_today: number;
  commissions_today: number;
}

/** Paper's two books (ADR 069); the two `day_pnl` add up to the account's. */
export interface PracticeBooks {
  you: PracticeBookDay;
  bots: PracticeBookDay & {
    budget_usd: number;
    budget_used_usd: number;
    by_bot: Record<string, PracticeBookDay>;
  };
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
  /** Paper (ADR 069): your book and the bots'; absent on Sim. */
  books?: PracticeBooks;
  working: IbkrOrder[];
  fills_today: number;
  schema_version: number;
  updated_at: string | null;
  /** Sim only: which replay this scratch ledger belongs to. */
  /** Sim only: the ledger's replay binding, `[source, symbol, date, start?, end?]` (or a legacy string). */
  replay_key?: string | ReadonlyArray<string | number | null> | null;
}
