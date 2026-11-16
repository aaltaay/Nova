import type { ISeriesApi } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { keepPriceDigits } from './chartPriceDigits';

const series = () => ({ applyOptions: vi.fn() }) as unknown as ISeriesApi<'Candlestick'>;

describe('keepPriceDigits', () => {
  it('reads a stock under $1 to four digits', () => {
    const s = series();
    keepPriceDigits(s, 0.3188);
    expect(s.applyOptions).toHaveBeenCalledWith({ priceFormat: { type: 'price', precision: 4, minMove: 0.0001 } });
  });

  it('goes back to cents when the pane changes to a dollar stock', () => {
    const s = series();
    keepPriceDigits(s, 0.3188);
    keepPriceDigits(s, 12.5);
    expect(s.applyOptions).toHaveBeenLastCalledWith({ priceFormat: { type: 'price', precision: 2, minMove: 0.01 } });
  });

  it('leaves the series alone while the digits stay the same', () => {
    const s = series();
    keepPriceDigits(s, 0.3188);
    keepPriceDigits(s, 0.3201);
    expect(s.applyOptions).toHaveBeenCalledTimes(1);
  });

  it('ignores a pane with no price yet', () => {
    const s = series();
    keepPriceDigits(s, undefined);
    keepPriceDigits(null, 0.3);
    expect(s.applyOptions).not.toHaveBeenCalled();
  });
});
