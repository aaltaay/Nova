import { beforeEach, describe, expect, it, vi } from 'vitest';
import { closeFullPosition } from './closeFullPosition';
import * as placeOrder from './placeOrder';

describe('closeFullPosition', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('rejects empty position without calling place', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder');
    const res = await closeFullPosition('AAPL', 0);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toMatch(/No open position/i);
    expect(spy).not.toHaveBeenCalled();
  });

  it('places a full SELL market exit for a long via placeIbkrOrder', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 99,
      error: null,
      mode: 'paper',
    });
    const res = await closeFullPosition('aapl', 150, { outsideRth: false });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.side).toBe('SELL');
      expect(res.qty).toBe(150);
      expect(res.order_id).toBe(99);
      expect(res.outside_rth).toBe(false);
    }
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: 'AAPL',
        side: 'SELL',
        qty: 150,
        order_type: 'MKT',
        outside_rth: false,
      }),
      undefined,
      expect.objectContaining({
        timing: expect.any(Object),
      }),
    );
  });

  it('places flatten with outside_rth when requested (extended hours)', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 11,
      error: null,
      mode: 'paper',
    });
    const res = await closeFullPosition('AAPL', 10, { outsideRth: true });
    expect(res.ok).toBe(true);
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ order_type: 'MKT', outside_rth: true }),
      undefined,
      expect.objectContaining({
        timing: expect.any(Object),
      }),
    );
  });

  it('places a full BUY market cover for a short', async () => {
    vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 7,
      error: null,
    });
    const res = await closeFullPosition('XYZ', -40, { outsideRth: false });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.side).toBe('BUY');
      expect(res.qty).toBe(40);
    }
  });
});
