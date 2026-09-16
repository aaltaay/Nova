import { describe, expect, it } from 'vitest';
import type { IbkrOrder } from './types';
import { planFillWorkingOrder } from './planFillWorkingOrder';

const FTFT: IbkrOrder = {
  order_id: 115067,
  symbol: 'ftft',
  side: 'SELL',
  qty: 1,
  filled_qty: 0,
  remaining_qty: 1,
  order_type: 'MKT',
  limit_price: null,
  status: 'Submitted',
  outside_rth: true,
};

describe('planFillWorkingOrder', () => {
  it('markets remaining qty during regular hours', () => {
    const plan = planFillWorkingOrder(FTFT, { sessionKind: 'rth' });
    expect(plan).toMatchObject({
      ok: true,
      qty: 1,
      side: 'SELL',
      symbol: 'FTFT',
      order_type: 'MKT',
      outside_rth: true,
    });
    if (plan.ok) {
      expect(plan.confirmMessage).toMatch(/fill the remaining shares/);
    }
  });

  it('refuses a premarket MKT when the desk book is on another symbol', () => {
    const plan = planFillWorkingOrder(FTFT, {
      sessionKind: 'premarket',
      book: { symbol: 'MEDS', bid: 6.5, ask: 6.7 },
    });
    expect(plan.ok).toBe(false);
    if (!plan.ok) {
      expect(plan.error).toMatch(/does not fill market orders in premarket/i);
      expect(plan.error).toMatch(/will not cancel and resubmit/);
      expect(plan.error).toMatch(/FTFT/);
      expect(plan.error).not.toMatch(/sweep FTFT -- no live bid \(desk book/);
    }
  });

  it('refuses a premarket LMT when there is no live bid', () => {
    const plan = planFillWorkingOrder(
      { ...FTFT, order_type: 'LMT', limit_price: 6 },
      { sessionKind: 'premarket' },
    );
    expect(plan.ok).toBe(false);
    if (!plan.ok) {
      expect(plan.error).toMatch(/cannot sweep FTFT -- no live bid/);
      expect(plan.error).toMatch(/was not cancelled/);
    }
  });

  it('names the wrong-symbol book on a premarket LMT', () => {
    const plan = planFillWorkingOrder(
      { ...FTFT, order_type: 'LMT', limit_price: 6 },
      {
        sessionKind: 'premarket',
        book: { symbol: 'MEDS', bid: 6.5, ask: 6.7 },
      },
    );
    expect(plan.ok).toBe(false);
    if (!plan.ok) {
      expect(plan.error).toMatch(/desk book is on MEDS/);
    }
  });

  it('sweeps a premarket SELL at the live bid', () => {
    const plan = planFillWorkingOrder(FTFT, {
      sessionKind: 'premarket',
      book: { symbol: 'FTFT', bid: 6.67, ask: 6.8 },
    });
    expect(plan).toMatchObject({
      ok: true,
      order_type: 'LMT',
      limit_price: 6.67,
      outside_rth: true,
      side: 'SELL',
      qty: 1,
    });
    if (plan.ok) {
      expect(plan.confirmMessage).toMatch(/sweep SELL 1 FTFT at bid \$6\.67/);
      expect(plan.confirmMessage).toMatch(/does not fill market orders/);
    }
  });

  it('sweeps a premarket BUY at the live ask', () => {
    const plan = planFillWorkingOrder(
      { ...FTFT, side: 'BUY', order_type: 'LMT', limit_price: 6 },
      {
        sessionKind: 'premarket',
        book: { symbol: 'FTFT', bid: 6.5, ask: 6.8 },
      },
    );
    expect(plan).toMatchObject({
      ok: true,
      order_type: 'LMT',
      limit_price: 6.8,
      side: 'BUY',
    });
    if (plan.ok) {
      expect(plan.confirmMessage).toMatch(/at ask \$6\.80/);
    }
  });

  it('ignores a zero or missing opposite quote', () => {
    const plan = planFillWorkingOrder(FTFT, {
      sessionKind: 'afterhours',
      book: { symbol: 'FTFT', bid: 0, ask: 6.8 },
    });
    expect(plan.ok).toBe(false);
    if (!plan.ok) {
      expect(plan.error).toMatch(/after-hours/);
    }
  });

  it('does not place when nothing remains', () => {
    const plan = planFillWorkingOrder(
      { ...FTFT, remaining_qty: 0, filled_qty: 1 },
      { sessionKind: 'rth' },
    );
    expect(plan).toEqual({ ok: false, error: 'Nothing left to fill on this order' });
  });
});
