/**
 * Nova Marketing Sample Data account snapshot (?view=sample).
 *
 * Owned here rather than in IbkrAccountContext so the sample desk's figures are
 * a fixture, not a side note on the live provider (#357). Types are imported
 * type-only, so nothing in this module can pull the live poller into the graph.
 *
 * The numbers reconcile with the SMPL sample position on purpose:
 *   NetLiquidation (100,000) = TotalCashValue (99,150) + GrossPositionValue (850)
 *   UnrealizedPnL (230)      = (4.25 market - 3.10 avg) * 200 shares
 * Day P&L in the header is RealizedPnL + UnrealizedPnL
 * (components/globalBarMoney.dayPnlFromSummary), which returns `--` only when
 * BOTH are absent -- so `RealizedPnL: 0` is here because a sample desk that has
 * closed nothing today has realized zero, not because omitting it would blank
 * the header. What actually made the header render `--` was the summary
 * carrying no P&L fields at all.
 */
import type { IbkrAccountState } from '../ibkr/IbkrAccountContext';
import type { IbkrAccountSummary } from '../ibkr/types';

export const SAMPLE_SUMMARY: IbkrAccountSummary = {
  connected: true,
  mode: 'paper',
  NetLiquidation: 100_000,
  BuyingPower: 50_000,
  TotalCashValue: 99_150,
  GrossPositionValue: 850,
  UnrealizedPnL: 230,
  RealizedPnL: 0,
  // Sample desk is a margin paper fixture so Side can show Short (#184).
  // Live desks use stamped account_class / shortSideVisible -- never AccountType=INDIVIDUAL.
  AccountType: 'MARGIN',
  account_class: 'margin',
};

export const SAMPLE_IBKR_ACCOUNT_STATE: IbkrAccountState = {
  summary: SAMPLE_SUMMARY,
  positions: [
    {
      symbol: 'SMPL',
      qty: 200,
      market_price: 4.25,
      market_value: 850,
      avg_cost: 3.1,
      unrealized_pnl: 230,
      realized_pnl: 0,
    },
  ],
  orders: [],
  closedOrders: [],
  loading: false,
  error: null,
  stale: false,
  staleSince: null,
  refresh: () => {},
};
