import { describe, expect, it } from 'vitest';
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import { tickerSuggestions } from './tickerSearchSuggestions';

/** Only the tables the search reads; scanner fractions (0.32 = +32%). */
function rows(partial: Partial<Record<'gappers' | 'gainers' | 'losers' | 'afterhours' | 'catalysts', object[]>>) {
  return {
    gappers: [],
    gainers: [],
    losers: [],
    afterhours: [],
    catalysts: [],
    ...partial,
  } as unknown as ScannerDockRows;
}

describe('tickerSuggestions', () => {
  it('offers nothing for an empty query', () => {
    expect(tickerSuggestions('  ', { tabs: ['AAPL'], positions: [], rows: null }, 8)).toEqual([]);
  });

  it('matches by prefix in the desk order: tabs, positions, then the scanner tables', () => {
    const found = tickerSuggestions('a', {
      tabs: ['', 'AMD', 'TSLA'],
      positions: [{ symbol: 'AAL', qty: 100 }, { symbol: 'ABNB', qty: 0 }],
      rows: rows({
        gappers: [{ symbol: 'AEHR', gap_percent: 0.32, change_pct: null }],
        gainers: [{ symbol: 'AMD', gap_percent: 0.05, change_pct: 0.05 }],
        catalysts: [{ symbol: 'ACHR', gap_percent: 0.11 }],
      }),
    }, 8);
    expect(found.map((s) => `${s.symbol}:${s.source}`)).toEqual([
      'AMD:tab',
      'AAL:position',
      'AEHR:gappers',
      'ACHR:catalysts',
    ]);
  });

  it('carries the move the scanner row knows, in percent points, and null when it knows none', () => {
    const found = tickerSuggestions('ae', {
      tabs: ['AE'],
      positions: [],
      rows: rows({ gappers: [{ symbol: 'AEHR', gap_percent: 0.32, change_pct: null }] }),
    }, 8);
    expect(found).toEqual([
      { symbol: 'AE', source: 'tab', movePct: null },
      { symbol: 'AEHR', source: 'gappers', movePct: 32 },
    ]);
  });

  it('puts the exact symbol first and keeps to the limit', () => {
    const found = tickerSuggestions('aa', {
      tabs: ['AAPL', 'AAOI', 'AA'],
      positions: [],
      rows: rows({ gappers: [{ symbol: 'AAL' }, { symbol: 'AAME' }] }),
    }, 3);
    expect(found.map((s) => s.symbol)).toEqual(['AA', 'AAPL', 'AAOI']);
  });
});
