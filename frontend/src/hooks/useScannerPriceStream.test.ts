import { describe, expect, it } from 'vitest';
import {
  applyScannerPricePatch,
  isRowQuoteStale,
} from './useScannerPriceStream';

describe('applyScannerPricePatch', () => {
  it('updates matching symbols and leaves others untouched', () => {
    const rows = [
      { symbol: 'NXTC', price: 6.0, change_pct: 1, volume: 10 },
      { symbol: 'MVO', price: 0.5, change_pct: 2, volume: 20 },
    ];
    const next = applyScannerPricePatch(rows, [
      { symbol: 'NXTC', price: 6.71, change_pct: 2.1, change_abs: 4.5, volume: 99 },
    ]);
    expect(next[0].price).toBe(6.71);
    expect(next[0].volume).toBe(99);
    expect(next[1]).toEqual(rows[1]);
  });

  it('returns the same array reference when nothing matches', () => {
    const rows = [{ symbol: 'AAPL', price: 1 }];
    expect(applyScannerPricePatch(rows, [{ symbol: 'MSFT', price: 2 }])).toBe(rows);
  });
});

describe('isRowQuoteStale', () => {
  it('uses per-row age so one fresh row cannot hide another stale row', () => {
    const now = 1000;
    const ages = { AAA: 999, BBB: 990 };
    expect(isRowQuoteStale('AAA', ages, now, false)).toBe(false);
    expect(isRowQuoteStale('BBB', ages, now, false)).toBe(true);
  });

  it('falls back to global stale when the row has never quoted', () => {
    expect(isRowQuoteStale('ZZZ', {}, 1000, true)).toBe(true);
    expect(isRowQuoteStale('ZZZ', {}, 1000, false)).toBe(false);
  });
});
