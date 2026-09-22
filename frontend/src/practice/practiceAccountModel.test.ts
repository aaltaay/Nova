import { describe, expect, it } from 'vitest';
import { dayPnlOf, isPracticeVenue } from './practiceAccountModel';

describe('isPracticeVenue', () => {
  it('is true only for paper and sim', () => {
    expect(isPracticeVenue('paper')).toBe(true);
    expect(isPracticeVenue('sim')).toBe(true);
    expect(isPracticeVenue('live')).toBe(false);
    expect(isPracticeVenue('disconnected')).toBe(false);
    expect(isPracticeVenue(null)).toBe(false);
    expect(isPracticeVenue(undefined)).toBe(false);
  });
});

describe('dayPnlOf', () => {
  it('prefers the wire day_pnl and falls back to realized + unrealized', () => {
    expect(dayPnlOf({ day_pnl: 5, realized_pnl: 1, unrealized_pnl: 1 })).toBe(5);
    expect(dayPnlOf({ day_pnl: Number.NaN, realized_pnl: 2, unrealized_pnl: -0.5 })).toBe(1.5);
    expect(dayPnlOf({ day_pnl: Number.NaN, realized_pnl: Number.NaN, unrealized_pnl: 4 })).toBe(4);
    expect(dayPnlOf({ day_pnl: Number.NaN, realized_pnl: Number.NaN, unrealized_pnl: Number.NaN })).toBeNull();
  });
});
