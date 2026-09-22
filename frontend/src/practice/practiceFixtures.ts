/** Test fixture: a Paper practice account as GET /api/practice/account returns it. */
import type { PracticeAccount } from './practiceTypes';

export const PAPER_ACCOUNT: PracticeAccount = {
  venue: 'paper',
  account_id: 'NOVA-PAPER',
  starting_cash: 100000,
  cash: 98750.5,
  buying_power: 395002,
  net_liquidation: 101200.25,
  gross_position_value: 2449.75,
  realized_pnl: 350.25,
  realized_today: 350.25,
  unrealized_pnl: -100,
  day_pnl: 250.25,
  day_started_et: '2026-09-21T04:00:00-04:00',
  commissions_today: 3.5,
  positions: [{ symbol: 'AAPL', qty: 10, avg_cost: 240, mark: 244.98, unrealized: -100 }],
  working: [],
  fills_today: 3,
  schema_version: 1,
  updated_at: '2026-09-21T10:00:00-04:00',
};
