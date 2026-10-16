import { describe, expect, it } from 'vitest';
import { DASH, duration, entered, etTime, exitPrice, exited, held, plAtStake, plPct, plPerShare, plTone, price, shortUsd, signedUsd } from './format';
import type { FollowedExit } from './types';

// 2026-10-13 10:42:07 EDT
const T = Date.UTC(2026, 9, 13, 14, 42, 7) / 1000;

function exit(over: Partial<FollowedExit>): FollowedExit {
  return { state: 'at', price: null, low: null, high: null, from_ts: null, to_ts: null, trade_ts: null, source: null,
    why: null, ...over };
}

describe('followed traders format', () => {
  it('writes times in New York', () => {
    expect(etTime(T)).toBe('10:42:07');
    expect(etTime(null)).toBe(DASH);
  });

  it('writes prices with cents, sub-dollar with four decimals', () => {
    expect(price(2.5)).toBe('2.50');
    expect(price(0.1234)).toBe('0.1234');
    expect(price(null)).toBe(DASH);
  });

  it('writes per-share P/L and percent, a range as a range', () => {
    expect(plPerShare({ per_share: 0.25, pct: 12.5 }, 2)).toBe('+0.25');
    expect(plPerShare({ per_share: 0.0125, pct: 2.5 }, 0.5)).toBe('+0.0125');
    expect(plPerShare({ per_share: -1.5, pct: -3 }, 50)).toBe('−1.50');
    expect(plPct({ per_share: -1.5, pct: -3 })).toBe('−3.00%');
    const range = { low_per_share: -0.3, high_per_share: 0.1, low_pct: -15, high_pct: 5 };
    expect(plPerShare(range, 2)).toBe('−0.30 to +0.10');
    expect(plPct(range)).toBe('−15.00% to +5.00%');
    expect(plTone(range)).toBe('flat');
    expect(plTone({ per_share: 0.2, pct: 1 })).toBe('up');
    expect(plPerShare(null, 2)).toBe(DASH);
  });

  it('writes what $1,000 in the trade would have made, a range as a range', () => {
    expect(plAtStake({ per_share: -0.02, pct: -2.63 })).toBe('−$26.30');
    expect(plAtStake({ per_share: 0.11, pct: 2.61 })).toBe('+$26.10');
    expect(plAtStake({ low_per_share: -0.3, high_per_share: 0.1, low_pct: -15, high_pct: 5 })).toBe('−$150.00 to +$50.00');
    expect(plAtStake({ per_share: 0, pct: 0 })).toBe('$0.00');
    expect(plAtStake(null)).toBe(DASH);
    expect(signedUsd(1234.5)).toBe('+$1,234.50');
    // A calendar square's: whole dollars, thousands as k.
    expect([shortUsd(45.4), shortUsd(-30), shortUsd(1234.5), shortUsd(-12_345), shortUsd(0.3)])
      .toEqual(['+$45', '−$30', '+$1.2k', '−$12k', '$0']);
  });

  it('writes how long it was held, saying what it cannot know', () => {
    expect(duration(45)).toBe('45s');
    expect(duration(725)).toBe('12m 05s');
    expect(duration(3720)).toBe('1h 02m');
    expect(held({ min_sec: 600, max_sec: 600 })).toBe('10m 00s');
    expect(held({ min_sec: 600, max_sec: null })).toBe('≥ 10m 00s');
    expect(held({ min_sec: 500, max_sec: 700 })).toBe('8m 20s–11m 40s');
    expect(held({ min_sec: null, max_sec: null })).toBe(DASH);
  });

  it('writes entries and exits the feed saw late as what they are', () => {
    const entry = { first_price: 1, avg_price: 1, ts: T, since_ts: null, known: true };
    expect(entered(entry)).toBe('10:42:07');
    expect(entered({ ...entry, known: false })).toBe('by 10:42:07');
    expect(entered({ ...entry, since_ts: T - 60 })).toBe('10:41:07–10:42:07');
    expect(exited(exit({ to_ts: T, from_ts: T - 300 }))).toBe('10:37:07–10:42:07');
  });

  it('never invents a fill for a window exit', () => {
    expect(exitPrice(exit({ state: 'at', price: 1.9 }))).toBe('1.90');
    expect(exitPrice(exit({ state: 'range', low: 1.7, high: 1.9 }))).toBe('1.70–1.90');
    expect(exitPrice(exit({ state: 'pending' }))).toBe('reading tape…');
    expect(exitPrice(exit({ state: 'pending', why: 'IBKR is not connected' }))).toBe('waiting for IBKR');
    expect(exitPrice(exit({ state: 'unavailable' }))).toBe('no price');
  });
});
