import { describe, expect, it } from 'vitest';
import {
  dayPnlFromSummary,
  formatSignedMoney,
  pnlToneClass,
} from './globalBarMoney';

describe('globalBarMoney', () => {
  it('sums realized + unrealized for Day P&L', () => {
    expect(dayPnlFromSummary(1.5, -0.25)).toBe(1.25);
    expect(dayPnlFromSummary(null, -0.17)).toBe(-0.17);
    expect(dayPnlFromSummary(2, null)).toBe(2);
    expect(dayPnlFromSummary(null, null)).toBeNull();
  });

  it('formats signed money with ASCII placeholders', () => {
    expect(formatSignedMoney(12.5)).toBe('+$12.50');
    expect(formatSignedMoney(-0.17)).toBe('-$0.17');
    expect(formatSignedMoney(0)).toBe('$0.00');
    expect(formatSignedMoney(null)).toBe('--');
  });

  it('picks tone classes for up / down / flat', () => {
    expect(pnlToneClass(1)).toBe('global-app-bar__tone--up');
    expect(pnlToneClass(-1)).toBe('global-app-bar__tone--down');
    expect(pnlToneClass(0)).toBe('global-app-bar__tone--flat');
    expect(pnlToneClass(null)).toBe('global-app-bar__tone--flat');
  });
});
