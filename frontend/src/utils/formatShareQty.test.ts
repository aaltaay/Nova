import { describe, expect, it } from 'vitest';
import { formatShareQty } from './formatShareQty';

describe('formatShareQty', () => {
  it('keeps whole shares compact', () => {
    expect(formatShareQty(100)).toBe('100');
    expect(formatShareQty(0)).toBe('0');
  });

  it('shows fractional shares (IBKR leftover lots)', () => {
    expect(formatShareQty(0.0642)).toBe('0.0642');
    expect(formatShareQty(10.5)).toBe('10.5');
  });

  it('caps at trade-sizing decimals and trims trailing zeros', () => {
    expect(formatShareQty(1.23456)).toBe('1.2346');
    expect(formatShareQty(1.2)).toBe('1.2');
  });

  it('handles null / non-finite', () => {
    expect(formatShareQty(null)).toBe('—');
    expect(formatShareQty(undefined)).toBe('—');
    expect(formatShareQty(Number.NaN)).toBe('—');
  });
});
