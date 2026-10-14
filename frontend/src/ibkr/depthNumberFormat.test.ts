import { describe, expect, it } from 'vitest';
import { formatBandPrice, formatDepthNumber, formatDepthPrice } from './depthNumberFormat';

describe('existing depth numeric formats with shared locale formatters (#797)', () => {
  it.each([
    [10, '10.00'], [0.6789, '0.6789'], [0.007651, '0.0077'],
    [12345.6789, '12,345.6789'], [-10.0001, '-10.0001'], [0, '0.00'],
  ] as const)('formats depth price %s as %s', (price, expected) => {
    expect(formatDepthPrice(price)).toBe(expected);
  });

  it.each([[10, '10.00'], [10.0877, '10.09'], [12345.6789, '12,345.68']] as const)(
    'formats LULD band %s as %s', (price, expected) => { expect(formatBandPrice(price)).toBe(expected); },
  );

  it.each([[5800, '5,800'], [0, '0'], [1234.56789, '1,234.568'], [-1000, '-1,000']] as const)(
    'retains grouped-number defaults for %s', (number, expected) => { expect(formatDepthNumber(number)).toBe(expected); },
  );

  it('matches the prior native locale output across prices, sizes, rounding edges and negative zero', () => {
    const values = [-0, -12345.67895, 0.00005, 0.005, 1.23445, 9.995, 10.00001,
      1000, 1_000_000.12345, NaN, Infinity, -Infinity];
    for (const value of values) {
      expect(formatDepthPrice(value)).toBe(value.toLocaleString('en-US', {
        minimumFractionDigits: 2, maximumFractionDigits: 4,
      }));
      expect(formatBandPrice(value)).toBe(value.toLocaleString('en-US', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
      }));
      expect(formatDepthNumber(value)).toBe(value.toLocaleString('en-US'));
    }
  });
});
