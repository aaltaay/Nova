/**
 * UI-only sample closed orders for preview when Gateway has none.
 * Never treated as broker truth — same isolation pattern as mockWorkingOrders.
 */
import type { ClosedOrder } from './types';

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
    },
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
    },
  ];
}
