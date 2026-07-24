import { describe, expect, it } from 'vitest';
import {
  buildExitFullPosition,
  buildExitPositionPercent,
  FRACTIONAL_ORDER_API_MSG,
  isWholeShareQty,
} from './exitPosition';

describe('buildExitFullPosition', () => {
  it('sells a long position', () => {
    expect(buildExitFullPosition(100)).toEqual({ ok: true, side: 'SELL', qty: 100 });
  });

  it('buys to cover a short', () => {
    expect(buildExitFullPosition(-40)).toEqual({ ok: true, side: 'BUY', qty: 40 });
  });

  it('errors when flat', () => {
    expect(buildExitFullPosition(0).ok).toBe(false);
    expect(buildExitFullPosition(null).ok).toBe(false);
  });

  it('blocks fractional leftovers (IBKR Error 10243)', () => {
    const res = buildExitFullPosition(0.0642);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.error).toBe(FRACTIONAL_ORDER_API_MSG);
    expect(isWholeShareQty(0.0642)).toBe(false);
    expect(isWholeShareQty(1)).toBe(true);
  });
});

describe('buildExitPositionPercent', () => {
  it('scales long exits', () => {
    expect(buildExitPositionPercent(100, 50)).toEqual({ ok: true, side: 'SELL', qty: 50 });
    expect(buildExitPositionPercent(100, 25)).toEqual({ ok: true, side: 'SELL', qty: 25 });
  });

  it('rejects invalid percent', () => {
    expect(buildExitPositionPercent(100, 0).ok).toBe(false);
    expect(buildExitPositionPercent(100, 101).ok).toBe(false);
  });
});
