import { describe, expect, it } from 'vitest';
import type { ClosedOrder } from '../closed_orders/types';
import type { IbkrOrder } from '../ibkr/types';
import {
  closedFilterFromToday,
  closedRowsForToday,
  filterWorkingForToday,
  ordersTodayBadgeCount,
  showWorkingForToday,
} from './filterOrdersToday';

const WORKING: IbkrOrder = {
  order_id: 1,
  symbol: 'AAPL',
  side: 'BUY',
  qty: 100,
  filled_qty: 0,
  remaining_qty: 100,
  order_type: 'LMT',
  limit_price: 10,
  status: 'Submitted',
};

const PARTIAL: IbkrOrder = {
  ...WORKING,
  order_id: 2,
  filled_qty: 40,
  remaining_qty: 60,
  avg_fill_price: 10.1,
};

describe('filterOrdersToday', () => {
  it('maps closed filters and working visibility', () => {
    expect(closedFilterFromToday('working')).toBeNull();
    expect(closedFilterFromToday('filled')).toBe('filled');
    expect(closedFilterFromToday('canceled')).toBe('cancelled');
    expect(closedFilterFromToday('partial_filled')).toBe('partial');
    expect(closedFilterFromToday('all')).toBe('all');
    expect(showWorkingForToday('working')).toBe(true);
    expect(showWorkingForToday('filled')).toBe(false);
  });

  it('filters working vs partial segments', () => {
    const rows = [WORKING, PARTIAL];
    expect(filterWorkingForToday(rows, 'working').map((o) => o.order_id)).toEqual([
      1, 2,
    ]);
    expect(
      filterWorkingForToday(rows, 'partial_filled').map((o) => o.order_id),
    ).toEqual([2]);
    expect(filterWorkingForToday(rows, 'filled')).toEqual([]);
    expect(filterWorkingForToday(rows, 'all', 'msft')).toEqual([]);
  });

  it('closedRowsForToday returns [] when the segment hides closed rows', () => {
    const closed: ClosedOrder[] = [{ ...WORKING, order_id: 3, status: 'Filled', filled_qty: 100 }];
    expect(closedRowsForToday(closed, 'working')).toEqual([]);
  });

  it('closedRowsForToday applies the same status + symbol filter as the panel', () => {
    const closed: ClosedOrder[] = [
      { ...WORKING, order_id: 3, status: 'Filled', filled_qty: 100 },
      { ...WORKING, order_id: 4, symbol: 'MSFT', status: 'Cancelled', filled_qty: 0 },
    ];
    expect(closedRowsForToday(closed, 'all', 'AAPL').map((o) => o.order_id)).toEqual([3]);
    expect(closedRowsForToday(closed, 'filled', 'AAPL').map((o) => o.order_id)).toEqual([3]);
    expect(closedRowsForToday(closed, 'canceled', 'AAPL')).toEqual([]);
  });

  it('ordersTodayBadgeCount sums working + closed for the active filter', () => {
    const closed: ClosedOrder[] = [
      { ...WORKING, order_id: 3, status: 'Filled', filled_qty: 100, remaining_qty: 0 },
    ];
    expect(ordersTodayBadgeCount([WORKING], closed, 'all', 'AAPL')).toBe(2);
    expect(ordersTodayBadgeCount([], closed, 'all', 'AAPL')).toBe(1);
    expect(ordersTodayBadgeCount([WORKING], closed, 'working', 'AAPL')).toBe(1);
    expect(ordersTodayBadgeCount([WORKING], closed, 'filled', 'AAPL')).toBe(1);
  });
});
