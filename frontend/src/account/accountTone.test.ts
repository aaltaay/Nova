import { describe, expect, it } from 'vitest';
import { PNL_TONE_MIN_USD } from '../constantGroups/account_page';
import { toneOf, toneOfKind } from './accountTone';

describe('account tones (operator ask, 2026-09-22: less red)', () => {
  it('tints P&L only once it moves the floor either way', () => {
    expect(PNL_TONE_MIN_USD).toBe(5);
    expect(toneOf(-0.53)).toBe('flat');
    expect(toneOf(-0.89)).toBe('flat');
    expect(toneOf(4.994)).toBe('flat');
    expect(toneOf(-5)).toBe('down');
    expect(toneOf(12)).toBe('up');
  });

  it('never tints a rounded zero or a missing figure', () => {
    expect(toneOf(-0)).toBe('flat');
    expect(toneOf(-0.004, 0)).toBe('flat');
    expect(toneOf(null)).toBe('flat');
    expect(toneOf(Number.NaN)).toBe('flat');
  });

  it('keeps costs muted and cash movements plain whatever their size', () => {
    expect(toneOfKind(-250, 'cost')).toBe('muted');
    expect(toneOfKind(-8.98, 'cash')).toBe('flat');
    expect(toneOfKind(100000, 'cash')).toBe('flat');
    expect(toneOfKind(-25, 'pnl')).toBe('down');
  });
});
