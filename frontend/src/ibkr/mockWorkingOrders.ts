/**
 * UI-only sample working orders for Open Orders preview (not sent to IBKR).
 * Covers every non-terminal IBKR status we map in formatOrderStatus, plus
 * partial-fill edge cases.
 *
 * Timestamps are fixed absolute ISO strings — never Date.now()-relative —
 * so the Time column does not crawl on every poll/re-render.
 */

import type { IbkrOrder } from './types';

/** IBKR openTrades-style statuses exercised by the sample set. */
export const MOCK_WORKING_IBKR_STATUSES = [
  'Submitted',
  'PendingSubmit',
  'PreSubmitted',
  'ApiPending',
] as const;

/** Fixed place-times for sample rows (UTC). Do not use relative "minutes ago". */
export const MOCK_WORKING_SUBMITTED = {
  90001: '2026-07-18T14:00:00.000Z',
  90002: '2026-07-18T14:15:00.000Z',
  90003: '2026-07-18T14:30:00.000Z',
  90004: '2026-07-18T14:45:00.000Z',
  90005: '2026-07-18T13:50:00.000Z',
  90006: '2026-07-18T14:50:00.000Z',
  90007: '2026-07-18T14:55:00.000Z',
  90008: '2026-07-18T15:00:00.000Z',
} as const;

/** Paper-style working rows for the open symbol — preview only. */
export function buildMockWorkingOrders(symbol: string): IbkrOrder[] {
  const sym = symbol.trim().toUpperCase() || 'DEMO';
  return [
    {
      order_id: 90001,
      symbol: sym,
      side: 'BUY',
      qty: 100,
      filled_qty: 0,
      remaining_qty: 100,
      order_type: 'LMT',
      limit_price: 24.1,
      stop_price: null,
      avg_fill_price: null,
      outside_rth: true,
      status: 'Submitted',
      submitted_at: MOCK_WORKING_SUBMITTED[90001],
      // updated_at may differ (fills) — Open Orders Time must ignore it.
      updated_at: '2026-07-18T15:59:59.000Z',
    },
    // Still working, only partially filled (most important open-order case).
    {
      order_id: 90002,
      symbol: sym,
      side: 'BUY',
      qty: 50,
      filled_qty: 20,
      remaining_qty: 30,
      order_type: 'LMT',
      limit_price: 24.25,
      stop_price: null,
      avg_fill_price: 24.24,
      outside_rth: false,
      status: 'Submitted',
      submitted_at: MOCK_WORKING_SUBMITTED[90002],
      updated_at: '2026-07-18T16:00:00.000Z',
    },
    {
      order_id: 90003,
      symbol: sym,
      side: 'SELL',
      qty: 75,
      filled_qty: 0,
      remaining_qty: 75,
      order_type: 'STP',
      limit_price: null,
      stop_price: 23.5,
      avg_fill_price: null,
      outside_rth: false,
      status: 'Submitted',
      submitted_at: MOCK_WORKING_SUBMITTED[90003],
      updated_at: MOCK_WORKING_SUBMITTED[90003],
    },
    {
      order_id: 90004,
      symbol: sym,
      side: 'BUY',
      qty: 25,
      filled_qty: 0,
      remaining_qty: 25,
      order_type: 'MKT',
      limit_price: null,
      stop_price: null,
      avg_fill_price: null,
      outside_rth: false,
      status: 'PendingSubmit',
      submitted_at: MOCK_WORKING_SUBMITTED[90004],
      updated_at: MOCK_WORKING_SUBMITTED[90004],
    },
    // Second partial: sell limit, Extended hours.
    {
      order_id: 90005,
      symbol: sym,
      side: 'SELL',
      qty: 100,
      filled_qty: 40,
      remaining_qty: 60,
      order_type: 'LMT',
      limit_price: 25.0,
      stop_price: null,
      avg_fill_price: 24.98,
      outside_rth: true,
      status: 'Submitted',
      submitted_at: MOCK_WORKING_SUBMITTED[90005],
      updated_at: '2026-07-18T16:01:00.000Z',
    },
    // PreSubmitted — pending at exchange (no fills yet).
    {
      order_id: 90006,
      symbol: sym,
      side: 'BUY',
      qty: 40,
      filled_qty: 0,
      remaining_qty: 40,
      order_type: 'LMT',
      limit_price: 23.9,
      stop_price: null,
      avg_fill_price: null,
      outside_rth: false,
      status: 'PreSubmitted',
      submitted_at: MOCK_WORKING_SUBMITTED[90006],
      updated_at: MOCK_WORKING_SUBMITTED[90006],
    },
    // PreSubmitted with partial fills (rare but UI must show Partially filled).
    {
      order_id: 90007,
      symbol: sym,
      side: 'SELL',
      qty: 60,
      filled_qty: 15,
      remaining_qty: 45,
      order_type: 'LMT',
      limit_price: 26.0,
      stop_price: null,
      avg_fill_price: 25.99,
      outside_rth: false,
      status: 'PreSubmitted',
      submitted_at: MOCK_WORKING_SUBMITTED[90007],
      updated_at: '2026-07-18T16:05:00.000Z',
    },
    // ApiPending — waiting on IB API ack.
    {
      order_id: 90008,
      symbol: sym,
      side: 'BUY',
      qty: 10,
      filled_qty: 0,
      remaining_qty: 10,
      order_type: 'LMT',
      limit_price: 24.0,
      stop_price: null,
      avg_fill_price: null,
      outside_rth: true,
      status: 'ApiPending',
      submitted_at: MOCK_WORKING_SUBMITTED[90008],
      updated_at: MOCK_WORKING_SUBMITTED[90008],
    },
  ];
}
