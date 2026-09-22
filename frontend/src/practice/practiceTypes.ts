/** Wire shape of GET /api/practice/account (ADR 020 "Contract"). */
import type { IbkrOrder } from '../ibkr/types';
import type { PracticeVenue } from '../constantGroups/practice';

export interface PracticePosition {
  symbol: string;
  qty: number;
  avg_cost: number | null;
  mark: number | null;
  unrealized: number | null;
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
  day_pnl: number;
  /** Realized P&L (net of fees) since the 04:00 ET practice-day boundary. */
  realized_today?: number | null;
  day_started_et: string | null;
  commissions_today: number;
  positions: PracticePosition[];
  working: IbkrOrder[];
  fills_today: number;
  schema_version: number;
  updated_at: string | null;
  /** Sim only: which replay this scratch ledger belongs to. */
  /** Sim only: the ledger's replay binding, `[source, symbol, date, start?, end?]` (or a legacy string). */
  replay_key?: string | ReadonlyArray<string | number | null> | null;
}
