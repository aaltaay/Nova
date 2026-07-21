import { describe, expect, it } from 'vitest';
import { filterClosedOrders } from './filterClosedOrders';
import type { ClosedOrder } from './types';

const ROWS: ClosedOrder[] = [
  {
    order_id: 1,
    symbol: 'AAPL',
    side: 'BUY',
    qty: 10,
    filled_qty: 10,
    remaining_qty: 0,
    order_type: 'MKT',
    limit_price: null,
    status: 'Filled',
  },
  {
    order_id: 2,
    symbol: 'MSFT',
    side: 'SELL',
    qty: 5,
    filled_qty: 0,
    remaining_qty: 0,
    order_type: 'LMT',
    limit_price: 1,
    status: 'Cancelled',
  },
  {
    order_id: 3,
    symbol: 'AAPL',
    side: 'BUY',
    qty: 2,
    filled_qty: 0,
    remaining_qty: 0,
    order_type: 'LMT',
    limit_price: 1,
    status: 'Inactive',
  },
  {
    order_id: 4,
    symbol: 'AAPL',
    side: 'BUY',
    qty: 100,
    filled_qty: 35,
    remaining_qty: 0,
    order_type: 'LMT',
    limit_price: 12.6,
    status: 'Cancelled',
  },
];

describe('filterClosedOrders', () => {
  it('filters by filled / cancelled / partial and symbol', () => {
    expect(filterClosedOrders(ROWS, 'filled').map((r) => r.order_id)).toEqual([1]);
    expect(filterClosedOrders(ROWS, 'cancelled').map((r) => r.order_id)).toEqual([
      2, 3,
    ]);
    expect(filterClosedOrders(ROWS, 'partial').map((r) => r.order_id)).toEqual([4]);
    expect(filterClosedOrders(ROWS, 'all', 'aapl').map((r) => r.order_id)).toEqual([
      1, 3, 4,
    ]);
  });
});
