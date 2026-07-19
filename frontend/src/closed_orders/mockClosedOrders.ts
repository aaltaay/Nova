/**
 * UI-only sample closed orders for preview when Gateway has none.
 * Never treated as broker truth — same isolation pattern as mockWorkingOrders.
 *
 * Includes cancel-after-partial so ops can rehearse inventory left after a
 * cancelled rest of order (does not live on Working Orders anymore).
 */
import type { ClosedOrder } from './types';

function isoMinutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

export function buildMockClosedOrders(symbol?: string | null): ClosedOrder[] {
  const sym = (symbol?.trim() || 'DEMO').toUpperCase();
  return [
    {
      order_id: 9001,
      symbol: sym,
      side: 'BUY',
      qty: 100,
      filled_qty: 100,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 12.5,
      stop_price: null,
      avg_fill_price: 12.48,
      outside_rth: false,
      status: 'Filled',
      submitted_at: isoMinutesAgo(95),
      updated_at: isoMinutesAgo(90),
    },
    {
      order_id: 9002,
      symbol: sym,
      side: 'SELL',
      qty: 50,
      filled_qty: 50,
      remaining_qty: 0,
      order_type: 'MKT',
      limit_price: null,
      stop_price: null,
      avg_fill_price: 13.1,
      outside_rth: false,
      status: 'Filled',
      submitted_at: isoMinutesAgo(70),
      updated_at: isoMinutesAgo(69),
    },
    // Cancelled with zero fills.
    {
      order_id: 9003,
      symbol: 'MSFT',
      side: 'BUY',
      qty: 25,
      filled_qty: 0,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 400,
      stop_price: null,
      avg_fill_price: null,
      outside_rth: true,
      status: 'Cancelled',
      submitted_at: isoMinutesAgo(40),
      updated_at: isoMinutesAgo(35),
    },
    // Critical: only part filled, then cancelled — inventory remains.
    {
      order_id: 9004,
      symbol: sym,
      side: 'BUY',
      qty: 100,
      filled_qty: 35,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 12.6,
      stop_price: null,
      avg_fill_price: 12.59,
      outside_rth: false,
      status: 'Cancelled',
      submitted_at: isoMinutesAgo(22),
      updated_at: isoMinutesAgo(8),
    },
    // ApiCancelled after a small partial (broker / API path).
    {
      order_id: 9005,
      symbol: sym,
      side: 'SELL',
      qty: 80,
      filled_qty: 10,
      remaining_qty: 0,
      order_type: 'LMT',
      limit_price: 13.4,
      stop_price: null,
      avg_fill_price: 13.38,
      outside_rth: false,
      status: 'ApiCancelled',
      submitted_at: isoMinutesAgo(15),
      updated_at: isoMinutesAgo(4),
    },
  ];
}
