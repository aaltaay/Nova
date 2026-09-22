import { beforeEach, describe, expect, it, vi } from 'vitest';
import { simClockResource } from '../sim/simClockResource';
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
        // QA R32: a protective flatten, never clamped to 1 share.
        intent: 'flatten',
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
    const res = await closeFullPosition('AAPL', 10, {
      outsideRth: true,
      book: { bid: 9.5, ask: 9.6, last: 9.55 },
    });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.outside_rth).toBe(true);
      expect(res.order_type).toBe('LMT');
    }
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({
        order_type: 'LMT',
        outside_rth: true,
        limit_price: 9.5,
      }),
      undefined,
      expect.objectContaining({
        timing: expect.any(Object),
      }),
    );
  });

  it('refuses after-hours flatten without a bid/ask/last', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder');
    const res = await closeFullPosition('AAPL', 10, { outsideRth: true });
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toMatch(/After-hours flatten/i);
    expect(spy).not.toHaveBeenCalled();
  });

  it('on Sim plans regular hours from the playhead, not the wall clock (QA R21)', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({ ok: true, order_id: 3, error: null, mode: 'sim' });
    // Playhead Mon 2026-09-21 13:05 ET (regular hours) while the wall clock is premarket.
    simClockResource.setData({ sim: true, live_edge: false, sim_time_et: '2026-09-21T13:05:00-04:00' });
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-09-22T09:00:00Z')); // 05:00 ET
    try {
      const res = await closeFullPosition('GRML', 2, { mode: 'sim', book: { bid: 9.3, ask: 9.31, last: 9.305 } });
      expect(res.ok && res.order_type).toBe('MKT');
      expect(spy).toHaveBeenCalledWith(expect.objectContaining({ order_type: 'MKT', outside_rth: false }), undefined, expect.anything());
      // The same wall clock on Paper plans the extended-hours limit.
      const paper = await closeFullPosition('GRML', 2, { mode: 'paper', book: { bid: 9.3, ask: 9.31, last: 9.305 } });
      expect(paper.ok && paper.order_type).toBe('LMT');
    } finally {
      vi.useRealTimers();
      simClockResource.setData(null);
    }
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
