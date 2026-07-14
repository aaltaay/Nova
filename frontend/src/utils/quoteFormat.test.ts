import { describe, expect, it } from 'vitest';
import { fmtSessionPrice, sessionPriceOrNull } from './quoteFormat';

describe('sessionPriceOrNull / fmtSessionPrice', () => {
  it('treats null and undefined as missing', () => {
    expect(sessionPriceOrNull(null)).toBeNull();
    expect(sessionPriceOrNull(undefined)).toBeNull();
    expect(fmtSessionPrice(null)).toBe('—');
  });

  it('treats 0 and negative as missing (never "$0.00")', () => {
    expect(sessionPriceOrNull(0)).toBeNull();
    expect(sessionPriceOrNull(-1)).toBeNull();
    expect(fmtSessionPrice(0)).toBe('—');
  });

  it('formats positive session prices', () => {
    expect(sessionPriceOrNull(8.28)).toBe(8.28);
    expect(fmtSessionPrice(8.28)).toBe('$8.28');
  });
});
