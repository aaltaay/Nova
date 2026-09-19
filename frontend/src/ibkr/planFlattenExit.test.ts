import { describe, expect, it } from 'vitest';
import { FLATTEN_EH_NO_MARK } from '../constants';
import { flattenSweepLimit, planFlattenExit } from './planFlattenExit';

// Friday 2026-09-18 10:30 ET = 14:30 UTC (EDT).
const RTH_FRIDAY = new Date('2026-09-18T14:30:00.000Z');
// Saturday 10:30 ET looks like clock-RTH if weekday is ignored.
const SATURDAY_CLOCK_RTH = new Date('2026-09-19T14:30:00.000Z');
// Friday 17:00 ET = 21:00 UTC.
const AH_FRIDAY = new Date('2026-09-18T21:00:00.000Z');

describe('planFlattenExit', () => {
  it('keeps weekday RTH as MKT outside_rth=false', () => {
    const ticket = planFlattenExit('SELL', { now: RTH_FRIDAY, book: { bid: 10 } });
    expect(ticket).toEqual({ ok: true, order_type: 'MKT', outside_rth: false });
  });

  it('treats Saturday clock-RTH as EH LMT at the bid', () => {
    const ticket = planFlattenExit('SELL', {
      now: SATURDAY_CLOCK_RTH,
      book: { bid: 9.5, ask: 9.6, last: 9.55 },
    });
    expect(ticket).toEqual({
      ok: true,
      order_type: 'LMT',
      outside_rth: true,
      limit_price: 9.5,
      quote_source: 'bid',
    });
  });

  it('covers a short after hours at the ask', () => {
    const ticket = planFlattenExit('BUY', {
      now: AH_FRIDAY,
      book: { bid: 10, ask: 10.2, last: 10.1 },
    });
    expect(ticket.ok).toBe(true);
    if (ticket.ok) {
      expect(ticket.order_type).toBe('LMT');
      expect(ticket.outside_rth).toBe(true);
      expect(ticket.limit_price).toBe(10.2);
      expect(ticket.quote_source).toBe('ask');
    }
  });

  it('falls back to last when the book is one-sided', () => {
    const ticket = planFlattenExit('SELL', {
      now: AH_FRIDAY,
      book: { last: 4.25 },
    });
    expect(ticket).toMatchObject({
      ok: true,
      order_type: 'LMT',
      outside_rth: true,
      limit_price: 4.25,
      quote_source: 'last',
    });
  });

  it('refuses an RTH-only MKT when after hours has no mark', () => {
    const ticket = planFlattenExit('SELL', { now: AH_FRIDAY });
    expect(ticket).toEqual({ ok: false, error: FLATTEN_EH_NO_MARK });
  });

  it('honors an explicit outsideRth=false pin (RTH flatten tests)', () => {
    const ticket = planFlattenExit('SELL', {
      now: SATURDAY_CLOCK_RTH,
      outsideRth: false,
    });
    expect(ticket).toEqual({ ok: true, order_type: 'MKT', outside_rth: false });
  });

  it('ignores non-positive sweep quotes', () => {
    expect(flattenSweepLimit('SELL', { bid: 0, last: -1 })).toBeNull();
  });
});
