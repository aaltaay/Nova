import { describe, expect, it } from 'vitest';
import {
  dayPnlFromSummary,
  formatSignedMoney,
  formatSignedPercent,
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

  it('picks tone classes for up / down / flat, neutral under the $5 floor', () => {
    expect(pnlToneClass(5)).toBe('global-app-bar__tone--up');
    expect(pnlToneClass(-12.5)).toBe('global-app-bar__tone--down');
    // A scratch trade or a commission-sized move is not an alarm (2026-09-22).
    expect(pnlToneClass(-0.53)).toBe('global-app-bar__tone--flat');
    expect(pnlToneClass(4.99)).toBe('global-app-bar__tone--flat');
    expect(pnlToneClass(0)).toBe('global-app-bar__tone--flat');
    expect(pnlToneClass(null)).toBe('global-app-bar__tone--flat');
    expect(pnlToneClass(-1, 1)).toBe('global-app-bar__tone--down');
  });

  it('never prints a sign on a figure that rounds to zero', () => {
    expect(formatSignedMoney(-0)).toBe('$0.00');
    expect(formatSignedMoney(-0.004)).toBe('$0.00');
    expect(formatSignedMoney(-0.006)).toBe('-$0.01');
    expect(formatSignedPercent(-0.0004)).toBe('0.00%');
    expect(formatSignedPercent(-0.53)).toBe('-0.53%');
  });
});
