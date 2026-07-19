/**
 * UI-only sample working orders for Open Orders preview (not sent to IBKR).
 */

import type { IbkrOrder } from './types';

/** Five paper-style working rows for the open symbol — preview only. */
export function buildMockWorkingOrders(symbol: string): IbkrOrder[] {
  const sym = symbol.trim().toUpperCase() || 'DEMO';
  // Realistic mix of statuses / types around a mid-20s name (e.g. SDOT-style).
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
    },
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
      status: 'PreSubmitted',
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
    },
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
    },
  ];
}
