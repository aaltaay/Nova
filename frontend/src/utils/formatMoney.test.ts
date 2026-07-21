import { describe, expect, it } from 'vitest';
import { formatMoney } from './formatMoney';

describe('formatMoney', () => {
  it('formats with 2 decimals by default', () => {
    expect(formatMoney(12.5)).toBe('$12.50');
    expect(formatMoney(0)).toBe('$0.00');
  });

  it('adds thousands separators', () => {
    expect(formatMoney(12345.6)).toBe('$12,345.60');
  });

  it('supports a 0-decimal variant (account totals)', () => {
    expect(formatMoney(578, 0)).toBe('$578');
    expect(formatMoney(12345.6, 0)).toBe('$12,346');
  });

  it('handles null / non-finite', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney(Number.NaN)).toBe('—');
  });
});
