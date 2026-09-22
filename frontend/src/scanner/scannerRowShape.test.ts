import { describe, expect, it } from 'vitest';
import type { ScannerRow } from '../types/scanner';
import {
  applyHonestPricePatch,
  carryQuoteQuality,
  isNameOnlyRow,
  normalizeCatalystRows,
  normalizePatchRows,
  normalizeScannerRow,
  normalizeScannerRows,
  SCANNER_QUOTE_CLOSE_FALLBACK,
} from './scannerRowShape';

function row(symbol: string, over: Partial<ScannerRow> = {}): ScannerRow {
  return normalizeScannerRow({ symbol, price: 9.42, prev_close: 3.68, volume: 1_000, ...over })!;
}

describe('normalizeScannerRow (QA C8)', () => {
  it('drops a row without a usable symbol instead of crashing the Scanner view', () => {
    expect(normalizeScannerRow({ symbol: null, price: 1 })).toBeNull();
    expect(normalizeScannerRow({ symbol: '   ', price: 1 })).toBeNull();
    expect(normalizeScannerRow({ symbol: 7, price: 1 })).toBeNull();
    expect(normalizeScannerRow(null)).toBeNull();
    expect(normalizeScannerRow(['GRML'])).toBeNull();
    expect(normalizeScannerRows([{ symbol: null }, { symbol: 'grml' }])?.map((r) => r.symbol)).toEqual(['GRML']);
    expect(normalizeScannerRows({ gainers: [] })).toBeNull();
  });

  it('turns a price string, an exchange object and an "Infinity" short ratio into stated absences', () => {
    const out = normalizeScannerRow({
      symbol: 'GRML',
      price: '9.42',
      exchange: { code: 'NASDAQ' },
      short_ratio: 'Infinity',
      gap_percent: Number.NaN,
      rel_volume: Number.POSITIVE_INFINITY,
      has_news: 'yes',
    })!;
    expect(out.price).toBeNull();
    expect(out.exchange).toBeNull();
    expect(out.short_ratio).toBeNull();
    expect(out.gap_percent).toBeNull();
    expect(out.rel_volume).toBeNull();
    expect(out.has_news).toBe(false);
  });

  it('keeps real values, optional fields only when present, and unknown fields as they came', () => {
    const out = normalizeScannerRow({
      symbol: 'grml', price: 9.42, gap_percent: 1.5649, exchange: ' NASDAQ ', rvol_source: 'yfinance', custom: 3,
    }) as ScannerRow & { custom?: number };
    expect(out.symbol).toBe('GRML');
    expect(out.gap_percent).toBe(1.5649);
    expect(out.exchange).toBe('NASDAQ');
    expect(out.rvol_source).toBe('yfinance');
    expect(out.custom).toBe(3);
    expect('rvol' in out).toBe(false);
  });

  it('reads a name-only row volume of 0 as unknown, not zero (QA C37)', () => {
    const nameOnly = normalizeScannerRow({ symbol: 'SMX', price: null, volume: 0 })!;
    expect(isNameOnlyRow(nameOnly)).toBe(true);
    expect(nameOnly.volume).toBeNull();
    // A quoted row keeps a real 0.
    expect(normalizeScannerRow({ symbol: 'SMX', price: 1.2, volume: 0 })!.volume).toBe(0);
    expect(normalizeScannerRow({ symbol: 'SMX', price: null, current_price: 1.2, volume: 0 })!.volume).toBe(0);
  });
});

describe('normalizePatchRows (QA C5)', () => {
  it('skips a patch row whose symbol is null instead of replacing the desk', () => {
    const out = normalizePatchRows([{ symbol: null, price: 1.23 }, { symbol: 'grml', price: 9.5 }]);
    expect(out).toEqual([{ symbol: 'GRML', price: 9.5 }]);
    expect(normalizePatchRows('nope')).toEqual([]);
  });

  it('a price sent as a string is no update, not a crash', () => {
    const rows = [row('GRML')];
    const next = applyHonestPricePatch(rows, normalizePatchRows([{ symbol: 'GRML', price: '9.50' }]));
    expect(next[0].price).toBe(9.42);
  });

  it('keeps Large Cap explicit unknowns and leaves absent fields absent', () => {
    const [p] = normalizePatchRows([{ symbol: 'NVDA', rvol: 'x', price: 180 }]);
    expect(p.rvol).toBeNull();
    expect('atr_expansion' in p).toBe(false);
  });
});

describe('prior-close fallback (QA C50)', () => {
  it('stamps close_fallback from the patch and clears it on a real print', () => {
    const rows = [row('GRML')];
    const marked = applyHonestPricePatch(rows, normalizePatchRows([
      { symbol: 'GRML', price: 3.68, change_pct: 0, quote_quality: 'close_fallback' },
    ]));
    expect(marked[0].quote_quality).toBe(SCANNER_QUOTE_CLOSE_FALLBACK);
    expect(marked[0].price).toBe(3.68);
    const live = applyHonestPricePatch(marked, normalizePatchRows([{ symbol: 'GRML', price: 3.9 }]));
    expect(live[0].quote_quality).toBeNull();
    // A patch with no price leaves the mark alone.
    const volumeOnly = applyHonestPricePatch(marked, normalizePatchRows([{ symbol: 'GRML', volume: 5 }]));
    expect(volumeOnly[0].quote_quality).toBe(SCANNER_QUOTE_CLOSE_FALLBACK);
  });

  it('a roster replace keeps the mark while the price has not moved', () => {
    const prev = [{ ...row('GRML', { price: 3.68 }), quote_quality: SCANNER_QUOTE_CLOSE_FALLBACK }];
    const same = carryQuoteQuality(prev, [row('GRML', { price: 3.68 })]);
    expect(same[0].quote_quality).toBe(SCANNER_QUOTE_CLOSE_FALLBACK);
    const moved = carryQuoteQuality(prev, [row('GRML', { price: 3.9 })]);
    expect(moved[0].quote_quality).toBeUndefined();
  });
});

describe('normalizeCatalystRows', () => {
  it('drops symbol-less catalysts and keeps exchange text-only', () => {
    const out = normalizeCatalystRows([{ symbol: null }, { symbol: 'qnme', exchange: { x: 1 }, gap_percent: 0.2 }]);
    expect(out?.map((c) => [c.symbol, c.exchange])).toEqual([['QNME', null]]);
    expect(normalizeCatalystRows(null)).toBeNull();
  });
});
