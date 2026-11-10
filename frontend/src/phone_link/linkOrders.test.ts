import { describe, expect, it } from 'vitest';
import { closingOrder, orderStamp, refusalText, type OrderContext } from './linkOrders';
import { blockedWhy, buyBlockedWhy } from './linkOrdersPanel';

const ctx = (over: Partial<OrderContext> = {}): OrderContext => ({
  symbol: 'F',
  offsetMs: -129,
  instance: 'f5842c72cc74',
  book: { seq: 41, at: 1_794_344_000.5, bid: 12.01, ask: 12.02 },
  ...over,
});

describe("an order's stamp", () => {
  it("puts the tap on the PC's clock, so a phone that runs ahead is not judged on its own time", () => {
    // The phone is 129 ms ahead of the PC: a tap at phone time T happened at PC time T - 129.
    const stamp = orderStamp(ctx(), 1_794_344_001_000, 5_000);
    expect(stamp?.view.action_wall_ms).toBe(1_794_344_000_871);
    expect(stamp?.client_timing.action_wall_ms).toBe(1_794_344_000_871);
    expect(stamp?.client_timing.action_performance_ms).toBe(5_000);
  });

  it('carries the Level 2 version this device last received and the backend it came from', () => {
    const stamp = orderStamp(ctx(), 1_000, 1);
    expect(stamp?.view).toMatchObject({ schema_version: 1, symbol: 'F', instance: 'f5842c72cc74', book: { seq: 41, bid: 12.01, ask: 12.02 } });
  });

  it('is not made before the clock is measured', () => {
    expect(orderStamp(ctx({ offsetMs: null }), 1_000, 1)).toBeNull();
  });
});

describe("Nova's words for a refusal", () => {
  it('reads the phone door, the request guard and the order door', () => {
    expect(refusalText(409, { detail: { reason: 'PHONE_NOT_PAPER', error: 'The desk is on Live: the phone trades Paper only. Nothing was sent.' } }))
      .toBe('The desk is on Live: the phone trades Paper only. Nothing was sent.');
    expect(refusalText(403, { detail: 'Nova is view-only from another device', reason: 'REMOTE_VIEW_ONLY' })).toBe('Nova is view-only from another device');
    expect(refusalText(200, { ok: false, error: 'Your Level 2 was 1.2 s behind', reason_code: 'VIEW_STALE' })).toBe('Your Level 2 was 1.2 s behind');
    expect(refusalText(422, { detail: [{ msg: 'Field required' }] })).toBe('Nova did not accept that order as written.');
    expect(refusalText(502, null)).toBe('Nova answered 502.');
  });
});

describe('what closes a position', () => {
  it('sells a long, buys back a short, and sends nothing when flat', () => {
    expect(closingOrder({ qty: 100, position_side: 'long' })).toEqual({ side: 'SELL', qty: 100 });
    expect(closingOrder({ qty: 50, position_side: 'short' })).toEqual({ side: 'BUY', qty: 50 });
    expect(closingOrder({ qty: -50 })).toEqual({ side: 'BUY', qty: 50 });
    expect(closingOrder({ qty: 0 })).toBeNull();
    expect(closingOrder(undefined)).toBeNull();
  });
});

describe('why the order buttons are off', () => {
  const status = { pin_set: true, unlocked: true, expires_at: null, venue: 'paper', paper: true, armed: true };

  it('names the one thing to do next, and nothing when orders may go', () => {
    expect(blockedWhy(null, true)).toBe('Nova could not be reached.');
    expect(blockedWhy({ ...status, pin_set: false }, true)).toContain('tools/set_phone_pin.py');
    expect(blockedWhy({ ...status, unlocked: false }, true)).toBe('Locked. Enter your phone PIN.');
    expect(blockedWhy({ ...status, venue: 'live', paper: false }, true)).toContain('Paper only');
    expect(blockedWhy(status, false)).toContain('Press Start');
    expect(blockedWhy(status, true)).toBeNull();
  });

  it('holds Buy alone until this device has the clock and a Level 2 book', () => {
    expect(buyBlockedWhy(ctx())).toBeNull();
    expect(buyBlockedWhy(ctx({ book: null }))).toContain('No Level 2 received for F');
    expect(buyBlockedWhy(ctx({ instance: null }))).toContain('Sell, Flatten and Cancel still work');
    expect(buyBlockedWhy(ctx({ offsetMs: null }))).toContain('clock');
    expect(buyBlockedWhy(null)).toBeNull();
  });
});
