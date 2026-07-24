import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fillWorkingOrderImmediately } from './fillWorkingOrderImmediately';
import * as placeOrder from './placeOrder';
import type { IbkrOrder } from './types';

vi.mock('../api/novaFetch', () => ({
  novaFetch: vi.fn(),
}));

vi.mock('./extendedSession', () => ({
  shouldUseOutsideRth: (flag?: boolean | null) => Boolean(flag),
}));

import { novaFetch } from '../api/novaFetch';

const ORDER: IbkrOrder = {
  order_id: 42,
  symbol: 'aapl',
  side: 'BUY',
  qty: 100,
  filled_qty: 25,
  remaining_qty: 75,
  order_type: 'LMT',
  limit_price: 10,
  status: 'Submitted',
  outside_rth: true,
};

describe('fillWorkingOrderImmediately', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(novaFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, error: null }),
    } as Response);
  });

  it('cancels then markets remaining qty with outside_rth from the order', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 99,
      error: null,
      mode: 'paper',
    });
    const res = await fillWorkingOrderImmediately(ORDER);
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.qty).toBe(75);
      expect(res.side).toBe('BUY');
      expect(res.outside_rth).toBe(true);
      expect(res.place_order_id).toBe(99);
    }
    expect(novaFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ibkr/order/42'),
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: 'AAPL',
        side: 'BUY',
        qty: 75,
        order_type: 'MKT',
        outside_rth: true,
      }),
      undefined,
      expect.objectContaining({
        timing: expect.any(Object),
        referencePrice: 10,
      }),
    );
  });

  it('does not place when nothing remains', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder');
    const res = await fillWorkingOrderImmediately({
      ...ORDER,
      remaining_qty: 0,
      filled_qty: 100,
    });
    expect(res.ok).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });

  it('derives remaining from qty − filled when remaining_qty is null', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 11,
      error: null,
      mode: 'paper',
    });
    const res = await fillWorkingOrderImmediately({
      ...ORDER,
      remaining_qty: null,
      filled_qty: 40,
      qty: 100,
    });
    expect(res.ok).toBe(true);
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ qty: 60 }),
      undefined,
      expect.objectContaining({ timing: expect.any(Object) }),
    );
  });
});
