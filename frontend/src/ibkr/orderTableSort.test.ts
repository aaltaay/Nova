import { describe, expect, it } from 'vitest';
import type { IbkrOrder } from './types';
import {
  compareOrderField,
  cycleOrderSort,
  sortOrders,
} from './orderTableSort';

function row(
  partial: Partial<IbkrOrder> & Pick<IbkrOrder, 'order_id' | 'status'>,
): IbkrOrder {
  return {
    symbol: 'AAPL',
    side: 'BUY',
    qty: 100,
    filled_qty: 0,
    remaining_qty: 100,
    order_type: 'LMT',
    limit_price: 10,
    outside_rth: false,
    ...partial,
  };
}

describe('orderTableSort', () => {
  it('cycles primary sort; time starts descending', () => {
    expect(cycleOrderSort([], 'qty', false)).toEqual([{ key: 'qty', dir: 'asc' }]);
    expect(cycleOrderSort([{ key: 'qty', dir: 'asc' }], 'qty', false)).toEqual([
      { key: 'qty', dir: 'desc' },
    ]);
    expect(cycleOrderSort([{ key: 'qty', dir: 'desc' }], 'qty', false)).toEqual(
      [],
    );
    expect(cycleOrderSort([], 'time', false)).toEqual([
      { key: 'time', dir: 'desc' },
    ]);
    expect(cycleOrderSort([], 'filled_at', false)).toEqual([
      { key: 'filled_at', dir: 'desc' },
    ]);
  });

  it('supports Shift+click multi-sort stack', () => {
    const s1 = cycleOrderSort([], 'status', false);
    const s2 = cycleOrderSort(s1, 'qty', true);
    expect(s2).toEqual([
      { key: 'status', dir: 'asc' },
      { key: 'qty', dir: 'asc' },
    ]);
    const s3 = cycleOrderSort(s2, 'qty', true);
    expect(s3).toEqual([
      { key: 'status', dir: 'asc' },
      { key: 'qty', dir: 'desc' },
    ]);
    expect(cycleOrderSort(s3, 'qty', true)).toEqual([
      { key: 'status', dir: 'asc' },
    ]);
  });

  it('sorts by semantic status then qty', () => {
    const orders = [
      row({ order_id: 1, status: 'Filled', filled_qty: 100, remaining_qty: 0, qty: 50 }),
      row({ order_id: 2, status: 'Submitted', qty: 10 }),
      row({ order_id: 3, status: 'Submitted', qty: 200 }),
      row({ order_id: 4, status: 'PreSubmitted', qty: 5 }),
    ];
    const sorted = sortOrders(
      orders,
      [
        { key: 'status', dir: 'asc' },
        { key: 'qty', dir: 'desc' },
      ],
      'working',
    );
    expect(sorted.map((o) => o.order_id)).toEqual([3, 2, 4, 1]);
  });

  it('compares session Regular before Extended on asc', () => {
    const a = row({ order_id: 1, status: 'Submitted', outside_rth: false });
    const b = row({ order_id: 2, status: 'Submitted', outside_rth: true });
    expect(compareOrderField(a, b, 'session', 'working')).toBeLessThan(0);
  });

  it('sorts working time by submitted_at', () => {
    const orders = [
      row({
        order_id: 1,
        status: 'Submitted',
        submitted_at: '2026-07-19T15:00:00.000Z',
        updated_at: '2026-07-19T16:00:00.000Z',
      }),
      row({
        order_id: 2,
        status: 'Submitted',
        submitted_at: '2026-07-19T14:00:00.000Z',
        updated_at: '2026-07-19T17:00:00.000Z',
      }),
    ];
    const sorted = sortOrders(
      orders,
      [{ key: 'time', dir: 'asc' }],
      'working',
    );
    expect(sorted.map((o) => o.order_id)).toEqual([2, 1]);
  });

  it('sorts closed Time Placed by submitted_at (not updated_at)', () => {
    const orders = [
      row({
        order_id: 1,
        status: 'Filled',
        submitted_at: '2026-07-19T15:00:00.000Z',
        updated_at: '2026-07-19T10:00:00.000Z',
      }),
      row({
        order_id: 2,
        status: 'Filled',
        submitted_at: '2026-07-19T14:00:00.000Z',
        updated_at: '2026-07-19T18:00:00.000Z',
      }),
    ];
    const sorted = sortOrders(
      orders,
      [{ key: 'time', dir: 'asc' }],
      'closed',
    );
    expect(sorted.map((o) => o.order_id)).toEqual([2, 1]);
  });

  it('sorts closed Time Filled by filled_at, missing (never filled) last', () => {
    const orders = [
      row({
        order_id: 1,
        status: 'Filled',
        submitted_at: '2026-07-19T15:00:00.000Z',
        filled_at: '2026-07-19T15:05:00.000Z',
      }),
      row({
        order_id: 2,
        status: 'Cancelled',
        submitted_at: '2026-07-19T14:00:00.000Z',
        filled_at: null,
      }),
      row({
        order_id: 3,
        status: 'Filled',
        submitted_at: '2026-07-19T13:00:00.000Z',
        filled_at: '2026-07-19T13:02:00.000Z',
      }),
    ];
    const sorted = sortOrders(
      orders,
      [{ key: 'filled_at', dir: 'asc' }],
      'closed',
    );
    expect(sorted.map((o) => o.order_id)).toEqual([3, 1, 2]);
  });
});
