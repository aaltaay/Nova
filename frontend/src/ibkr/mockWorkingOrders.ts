/**
 * UI-only sample working orders for Open Orders preview (not sent to IBKR).
 * Includes partial-fill rows so we can rehearse the serious edge cases offline.
 */

import type { IbkrOrder } from './types';

function isoMinutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

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
      submitted_at: isoMinutesAgo(42),
      updated_at: isoMinutesAgo(42),
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
      submitted_at: isoMinutesAgo(28),
      updated_at: isoMinutesAgo(3),
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
      submitted_at: isoMinutesAgo(18),
      updated_at: isoMinutesAgo(18),
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
      submitted_at: isoMinutesAgo(1),
      updated_at: isoMinutesAgo(1),
    },
    // Second partial: sell limit, Extended hours, last fill a few seconds ago.
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
      submitted_at: isoMinutesAgo(55),
      updated_at: isoMinutesAgo(0.2),
    },
  ];
}
