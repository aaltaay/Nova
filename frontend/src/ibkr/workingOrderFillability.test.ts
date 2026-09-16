import { describe, expect, it } from 'vitest';
import type { IbkrOrder } from './types';
import { workingOrderStatusDisplay } from './workingOrderFillability';

const MKT: IbkrOrder = {
  order_id: 115067,
  symbol: 'FTFT',
  side: 'SELL',
  qty: 1,
  filled_qty: 0,
  remaining_qty: 1,
  order_type: 'MKT',
  limit_price: null,
  status: 'Submitted',
  outside_rth: true,
};

describe('workingOrderStatusDisplay', () => {
  it('keeps Working during regular hours', () => {
    expect(workingOrderStatusDisplay(MKT, 'Working', 'rth')).toEqual({
      label: 'Working',
      title: 'Submitted',
    });
  });

  it('marks a premarket MKT as waiting for the open', () => {
    const shown = workingOrderStatusDisplay(MKT, 'Working', 'premarket');
    expect(shown.label).toBe('Working (MKT waits for open)');
    expect(shown.title).toMatch(/does not fill market orders/i);
    expect(shown.title).toMatch(/bid on FTFT/);
  });

  it('prefers Warning 399 held-until when present', () => {
    const shown = workingOrderStatusDisplay(
      { ...MKT, held_until: '2026-09-16T13:30:00Z' },
      'Working',
      'premarket',
    );
    expect(shown.label).toBe('Working (held to open)');
    expect(shown.title).toMatch(/held until 2026-09-16T13:30:00Z/);
  });
});
