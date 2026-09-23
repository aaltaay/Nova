import { describe, expect, it } from 'vitest';
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import { buildSymbolDirectory } from './symbolDirectory';
import { looksLikeSymbol, parseTickerQuery } from './tickerSearchQuery';
import { searchTickers, tickerSuggestions } from './tickerSearchSuggestions';

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
    expect(found.map(({ symbol, source, movePct }) => ({ symbol, source, movePct }))).toEqual([
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

const DIRECTORY = buildSymbolDirectory([
  ['AAPL', 'Apple Inc. Common Stock', 'NASDAQ'],
  ['APLE', 'Apple Hospitality REIT, Inc.', 'NYSE'],
  ['PINE', 'Alpine Income Property Trust', 'NYSE'],
  ['A', 'Agilent Technologies Inc.', 'NYSE'],
  ['AA', 'Alcoa Corporation', 'NYSE'],
  ['AAL', 'American Airlines Group Inc.', 'NASDAQ'],
  ['AMD', 'Advanced Micro Devices, Inc.', 'NASDAQ'],
  ['SPY', 'SPDR S&P 500 ETF Trust', 'ARCA'],
  ['QQQ', 'Invesco QQQ Trust, Series 1', 'NASDAQ'],
  ['BRK.B', 'Berkshire Hathaway Inc.', 'NYSE'],
]);

function search(raw: string, pools: Partial<Parameters<typeof searchTickers>[1]> = {}, limit = 8) {
  return searchTickers(parseTickerQuery(raw), { tabs: [], positions: [], rows: null, directory: DIRECTORY, ...pools }, limit);
}

describe('searchTickers over the listed-symbol directory', () => {
  it('finds a symbol by company name, on a word boundary only', () => {
    const found = search('apple').suggestions;
    expect(found.map((s) => s.symbol)).toEqual(['AAPL', 'APLE']);
    expect(found[0]).toMatchObject({ source: 'listed', name: 'Apple Inc. Common Stock', exchange: 'NASDAQ', nameMatch: [0, 5] });
    // "Alpine" holds "pine" but not at a word start.
    expect(search('pine').suggestions.map((s) => s.symbol)).toEqual(['PINE']);
  });

  it('matches several words across punctuation', () => {
    expect(search('micro dev').suggestions.map((s) => s.symbol)).toEqual(['AMD']);
    expect(search('s p 500').suggestions.map((s) => s.symbol)).toEqual(['SPY']);
  });

  it('ranks exact, then symbol prefix (shortest first), then name', () => {
    expect(search('aa').suggestions.map((s) => s.symbol)).toEqual(['AA', 'AAL', 'AAPL']);
    const q = search('a').suggestions.map((s) => s.symbol);
    expect(q.slice(0, 3)).toEqual(['A', 'AA', 'AAL']);
  });

  it('keeps the desk first and labels it by its desk source, with the listing name', () => {
    const found = search('app', { recents: ['APLE'], tabs: ['AAPL'] }).suggestions;
    expect(found.map((s) => `${s.symbol}:${s.source}`)).toEqual(['AAPL:tab', 'APLE:recent']);
    expect(found[0].name).toBe('Apple Inc. Common Stock');
  });

  it('a regex matches symbols only and reports the full count past the limit', () => {
    const result = search('/^A/', {}, 2);
    expect(result.suggestions.map((s) => s.symbol)).toEqual(['A', 'AA']);
    expect(result.total).toBe(6);
    expect(search('/^q+$/').suggestions.map((s) => s.symbol)).toEqual(['QQQ']);
    expect(search('/TRUST/').total).toBe(0);
  });

  it('a wildcard spans the whole symbol', () => {
    expect(search('A*L').suggestions.map((s) => s.symbol)).toEqual(['AAL', 'AAPL']);
    expect(search('??Q').suggestions.map((s) => s.symbol)).toEqual(['QQQ']);
    expect(search('BRK.?').suggestions.map((s) => s.symbol)).toEqual(['BRK.B']);
  });

  it('offers nothing for an invalid pattern', () => {
    expect(search('/[/').suggestions).toEqual([]);
  });
});

describe('parseTickerQuery', () => {
  it('tells text, regex, wildcard and mistakes apart', () => {
    expect(parseTickerQuery('  ')).toEqual({ kind: 'empty' });
    expect(parseTickerQuery(' apple  inc ')).toEqual({ kind: 'text', text: 'APPLE INC' });
    expect(parseTickerQuery('/^a.x$/')).toMatchObject({ kind: 'pattern', flavor: 'regex' });
    expect(parseTickerQuery('/^a.x$')).toMatchObject({ kind: 'pattern', flavor: 'regex' });
    expect(parseTickerQuery('a*')).toMatchObject({ kind: 'pattern', flavor: 'wildcard' });
    expect(parseTickerQuery('/')).toMatchObject({ kind: 'invalid' });
    expect(parseTickerQuery('/(')).toMatchObject({ kind: 'invalid' });
    expect(parseTickerQuery('a*$')).toMatchObject({ kind: 'invalid' });
    expect(parseTickerQuery(`/${'a'.repeat(80)}/`)).toMatchObject({ kind: 'invalid' });
  });

  it('only a ticker-shaped text earns the typed row', () => {
    expect(looksLikeSymbol('AAPL')).toBe(true);
    expect(looksLikeSymbol('BRK.B')).toBe(true);
    expect(looksLikeSymbol('APPLE INC')).toBe(false);
    expect(looksLikeSymbol('ABCDEFGHIJKL')).toBe(false);
  });
});
