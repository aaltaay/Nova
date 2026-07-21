/**
 * Frozen Open/Closed order fixtures for Playwright (L3 pyramid).
 * Numbers aligned with unit / API contract tests — no Date.now().
 */

export const E2E_WORKING_PARTIAL = {
  order_id: 4242,
  symbol: 'AAPL',
  side: 'BUY' as const,
  qty: 100,
  filled_qty: 40,
  remaining_qty: 60,
  order_type: 'LMT',
  limit_price: 190.55,
  stop_price: null,
  avg_fill_price: 190.42,
  outside_rth: false,
  status: 'Submitted',
  submitted_at: '2026-07-18T13:41:23.000Z',
  // Deliberately different — Open Orders Time must ignore this.
  updated_at: '2026-07-18T18:00:00.000Z',
};

export const E2E_CLOSED_FILLED = {
  order_id: 9001,
  symbol: 'AAPL',
  side: 'BUY' as const,
  qty: 100,
  filled_qty: 100,
  remaining_qty: 0,
  order_type: 'LMT',
  limit_price: 12.5,
  stop_price: null,
  avg_fill_price: 12.48,
  outside_rth: false,
  status: 'Filled',
  submitted_at: '2026-07-18T13:00:00.000Z',
  updated_at: '2026-07-18T13:41:23.000Z',
};

export const E2E_CLOSED_PARTIAL_CANCEL = {
  order_id: 9004,
  symbol: 'AAPL',
  side: 'BUY' as const,
  qty: 100,
  filled_qty: 35,
  remaining_qty: 0,
  order_type: 'LMT',
  limit_price: 12.6,
  stop_price: null,
  avg_fill_price: 12.59,
  outside_rth: false,
  status: 'Cancelled',
  submitted_at: '2026-07-18T12:00:00.000Z',
  updated_at: '2026-07-18T12:30:00.000Z',
};

export const E2E_CLOSED_API_CANCELLED = {
  order_id: 9006,
  symbol: 'AAPL',
  side: 'BUY' as const,
  qty: 20,
  filled_qty: 0,
  remaining_qty: 0,
  order_type: 'STP',
  limit_price: null,
  stop_price: 11.5,
  avg_fill_price: null,
  outside_rth: false,
  status: 'ApiCancelled',
  submitted_at: '2026-07-18T13:00:00.000Z',
  updated_at: '2026-07-18T13:01:00.000Z',
};

export const E2E_CLOSED_INACTIVE = {
  order_id: 9007,
  symbol: 'AAPL',
  side: 'SELL' as const,
  qty: 30,
  filled_qty: 0,
  remaining_qty: 0,
  order_type: 'LMT',
  limit_price: 14.0,
  stop_price: null,
  avg_fill_price: null,
  outside_rth: false,
  status: 'Inactive',
  submitted_at: '2026-07-18T13:10:00.000Z',
  updated_at: '2026-07-18T13:12:00.000Z',
};

export const E2E_WORKING_PRESUBMITTED = {
  order_id: 4243,
  symbol: 'AAPL',
  side: 'BUY' as const,
  qty: 40,
  filled_qty: 0,
  remaining_qty: 40,
  order_type: 'LMT',
  limit_price: 23.9,
  stop_price: null,
  avg_fill_price: null,
  outside_rth: false,
  status: 'PreSubmitted',
  submitted_at: '2026-07-18T14:50:00.000Z',
  updated_at: '2026-07-18T14:50:00.000Z',
};

export const E2E_WORKING_API_PENDING = {
  order_id: 4244,
  symbol: 'AAPL',
  side: 'BUY' as const,
  qty: 10,
  filled_qty: 0,
  remaining_qty: 10,
  order_type: 'LMT',
  limit_price: 24.0,
  stop_price: null,
  avg_fill_price: null,
  outside_rth: true,
  status: 'ApiPending',
  submitted_at: '2026-07-18T15:00:00.000Z',
  updated_at: '2026-07-18T15:00:00.000Z',
};

export const E2E_IBKR_STATUS = {
  enabled: true,
  connected: true,
  mode: 'paper',
  gateway_mode: 'paper',
  broker_account_kind: 'paper',
  orders_enabled: true,
  live_trading_confirmed: false,
  spend_status: 'paper_armed',
  gateway_self_heal_enabled: true,
  gateway_self_heal: null,
};

export const E2E_ACCOUNT = {
  connected: true,
  mode: 'paper',
  NetLiquidation: 100_000,
  BuyingPower: 100_000,
  pending: false,
};

/** Paper long — Stock View Positions dock (WID-019). */
export const E2E_POSITION_AAPL = {
  symbol: 'AAPL',
  qty: 100,
  market_price: 191.2,
  market_value: 19_120,
  avg_cost: 190.0,
  unrealized_pnl: 120,
  realized_pnl: 0,
};
