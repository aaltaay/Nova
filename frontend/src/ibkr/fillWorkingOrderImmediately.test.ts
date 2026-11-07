import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  confirmAndFillWorkingOrder,
  fillWorkingOrderImmediately,
} from './fillWorkingOrderImmediately';
import { noteBackendGate, resetViewRegistryForTests } from '../market_view/viewRegistry';
import * as placeOrder from './placeOrder';
import type { IbkrOrder } from './types';

vi.mock('../api/novaFetch', () => ({
  novaFetch: vi.fn(),
}));

vi.mock('../ux', () => ({
  confirmApp: vi.fn(),
}));

const desk = vi.hoisted(() => ({ venue: 'paper' as string | null }));

vi.mock('./confirmedDeskVenue', () => ({
  getConfirmedDeskVenueSnapshot: () => ({ venue: desk.venue, generation: null }),
}));

import { novaFetch } from '../api/novaFetch';
import { confirmApp } from '../ux';

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

const FTFT: IbkrOrder = {
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

describe('fillWorkingOrderImmediately', () => {
  beforeEach(() => {
    // A gate one test noted never reaches the next (a failed assertion skips the reset at its end).
    resetViewRegistryForTests();
    vi.restoreAllMocks();
    vi.mocked(novaFetch).mockClear();
    vi.mocked(novaFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, error: null }),
    } as Response);
  });

  it('cancels then markets remaining qty during regular hours', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 99,
      error: null,
      mode: 'paper',
    });
    const res = await fillWorkingOrderImmediately(ORDER, undefined, {
      sessionKind: 'rth',
    });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.qty).toBe(75);
      expect(res.side).toBe('BUY');
      expect(res.outside_rth).toBe(true);
      expect(res.order_type).toBe('MKT');
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

  it('never cancels a resting short entry or re-sends it as a plain SELL (ADR 048 gap 7)', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder');
    const res = await fillWorkingOrderImmediately(
      { ...FTFT, order_type: 'LMT', limit_price: 6.7, short_entry: true },
      undefined,
      { sessionKind: 'rth', book: { symbol: 'FTFT', bid: 6.67, ask: 6.8 } },
    );
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toMatch(/does not short/);
    expect(novaFetch).not.toHaveBeenCalled();
    expect(spy).not.toHaveBeenCalled();
  });

  it('does not cancel a premarket MKT when there is no live bid', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder');
    const res = await fillWorkingOrderImmediately(FTFT, undefined, {
      sessionKind: 'premarket',
      book: { symbol: 'MEDS', bid: 6.5, ask: 6.7 },
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/will not cancel and resubmit/);
    }
    expect(novaFetch).not.toHaveBeenCalled();
    expect(spy).not.toHaveBeenCalled();
  });

  it('cancels then sweeps a premarket SELL at the live bid', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 115200,
      error: null,
      mode: 'paper',
    });
    const res = await fillWorkingOrderImmediately(FTFT, undefined, {
      sessionKind: 'premarket',
      book: { symbol: 'FTFT', bid: 6.67, ask: 6.8 },
    });
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.order_type).toBe('LMT');
      expect(res.limit_price).toBe(6.67);
      expect(res.outside_rth).toBe(true);
    }
    expect(novaFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ibkr/order/115067'),
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: 'FTFT',
        side: 'SELL',
        qty: 1,
        order_type: 'LMT',
        limit_price: 6.67,
        outside_rth: true,
      }),
      undefined,
      expect.objectContaining({
        referencePrice: 6.67,
      }),
    );
  });

  it('a lag holds Fill now on a working buy, never on a working sell (ADR 045 amendment 2026-11-06)', async () => {
    const cancel = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({ ok: true, order_id: 7 } as never);
    (novaFetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true, status: 200, json: async () => ({ ok: true }),
    } as never);
    noteBackendGate('AAPL', { code: 'TAPE_STALE', text: "AAPL's Time & Sales is behind." });
    // The session is pinned: read from the clock, an evening run plans an overnight sweep, which refuses the
    // buy for its missing ask before the lag is ever asked (PR #1302 CI, 21:05 ET).
    const rth = { sessionKind: 'rth' as const };
    const held = await fillWorkingOrderImmediately(ORDER, undefined, rth);
    expect(held).toEqual({ ok: false, error: "AAPL's Time & Sales is behind." });
    expect(novaFetch).not.toHaveBeenCalled();

    const sold = await fillWorkingOrderImmediately({ ...ORDER, side: 'SELL' }, undefined, rth);
    expect(sold.ok).toBe(true);
    const cover = await fillWorkingOrderImmediately({ ...ORDER, effect: 'closes' }, undefined, rth);
    expect(cover.ok).toBe(true);
    resetViewRegistryForTests();
    cancel.mockRestore();
  });

  it('does not place when nothing remains', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder');
    const res = await fillWorkingOrderImmediately({
      ...ORDER,
      remaining_qty: 0,
      filled_qty: 100,
    }, undefined, { sessionKind: 'rth' });
    expect(res.ok).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });

  it('derives remaining from qty − filled when remaining_qty is null', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 11,
      error: null,
    });
    const res = await fillWorkingOrderImmediately({
      ...ORDER,
      remaining_qty: null,
      filled_qty: 40,
      qty: 100,
    }, undefined, { sessionKind: 'rth' });
    expect(res.ok).toBe(true);
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ qty: 60 }),
      undefined,
      expect.objectContaining({ timing: expect.any(Object) }),
    );
  });
});

describe('confirmAndFillWorkingOrder', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(confirmApp).mockResolvedValue(true);
  });

  it('alerts with the plan error and never opens confirm when EH MKT cannot sweep', async () => {
    const res = await confirmAndFillWorkingOrder(FTFT, {
      sessionKind: 'premarket',
    });
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(res.error).toMatch(/does not fill market orders in premarket/);
    }
    expect(confirmApp).not.toHaveBeenCalled();
  });

  it('confirms a bid sweep before cancelling', async () => {
    vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({
      ok: true,
      order_id: 9,
      error: null,
    });
    vi.mocked(novaFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, error: null }),
    } as Response);
    const res = await confirmAndFillWorkingOrder(FTFT, {
      sessionKind: 'premarket',
      book: { symbol: 'FTFT', bid: 6.67, ask: 6.8 },
    });
    expect(confirmApp).toHaveBeenCalledWith(
      expect.objectContaining({
        message: expect.stringMatching(/sweep SELL 1 FTFT at bid \$6\.67/),
      }),
    );
    expect(res.ok).toBe(true);
  });

  it('names the venue of the click on its cancel and its fill, whatever the desk shows after the confirm (#1283)', async () => {
    desk.venue = 'paper';
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder').mockResolvedValue({ ok: true, order_id: 99, error: null });
    vi.mocked(confirmApp).mockImplementation(async () => {
      desk.venue = 'live'; // the desk moved while the confirm was open
      return true;
    });

    await confirmAndFillWorkingOrder(FTFT, {
      sessionKind: 'premarket',
      book: { symbol: 'FTFT', bid: 6.67, ask: 6.8 },
    });

    expect(String(vi.mocked(novaFetch).mock.calls[0][0])).toMatch(/\/api\/ibkr\/order\/115067\?venue=paper$/);
    expect(spy.mock.calls[0][0]).toMatchObject({ symbol: 'FTFT', venue: 'paper' });
    desk.venue = 'paper';
  });

  it('never fills on the venue the desk moved to: a cancel the door refuses ends it (#1283)', async () => {
    const spy = vi.spyOn(placeOrder, 'placeIbkrOrder');
    vi.mocked(confirmApp).mockResolvedValue(true);
    vi.mocked(novaFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: false, error: 'the desk is on live, not paper' }),
    } as Response);

    const res = await confirmAndFillWorkingOrder(FTFT, {
      sessionKind: 'premarket',
      book: { symbol: 'FTFT', bid: 6.67, ask: 6.8 },
    });

    expect(res).toMatchObject({ ok: false, error: 'the desk is on live, not paper' });
    expect(spy).not.toHaveBeenCalled();
  });
});
