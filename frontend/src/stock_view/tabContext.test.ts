import { describe, expect, it } from 'vitest';
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import type { ScannerRow } from '../types/scanner';
import { catalystInitial, formatSignedPct, pctTone, tabContextFor } from './tabContext';

function row(symbol: string, over: Partial<ScannerRow> = {}): ScannerRow {
  return {
    symbol, price: 1, prev_close: 1, change_pct: null, change_abs: null, gap_percent: null, volume: 0,
    rel_volume: null, has_news: false, newest_headline_at: null, market_cap: null, float: null,
    short_interest: null, short_ratio: null, ...over,
  };
}

const rows = (over: Partial<ScannerDockRows>): ScannerDockRows => ({
  gappers: [], gainers: [], losers: [], afterhours: [], catalysts: [], watchlistEntries: [],
  mode: 'market', health: { status: 'ok', latency_ms: 1 }, discoveryProvider: 'ibkr', pricesStale: false,
  flashSymbols: {}, rowQuoteTs: {}, nowSec: 0, tableMeta: {},
  counts: { gappers: 0, gainers: 0, losers: 0, afterhours: 0, catalysts: 0 }, setL1DockTab: null, ...over,
});

describe('tabContextFor', () => {
  it('is unknown (no gap, no chip) without a scanner row', () => {
    expect(tabContextFor('ZZZZ', rows({}))).toEqual({ gapPct: null, catalyst: null, headline: null, known: false, price: null });
    expect(tabContextFor('ZZZZ', null).known).toBe(false);
  });

  it('reads the gap from the first list that names the symbol and falls back to the day change', () => {
    const ctx = tabContextFor('grml', rows({ gainers: [row('GRML', { change_pct: 12.5, price: 8.9 })] }));
    expect(ctx.gapPct).toBe(12.5);
    expect(ctx.price).toBe(8.9);
    expect(ctx.known).toBe(true);
    expect(ctx.catalyst).toBeNull();
  });

  it('labels a company wire PR and everything else NEWS, with the headline for the tooltip', () => {
    const catalyst = {
      symbol: 'QNME', previous_close: 1, current_price: 1, gap_percent: 3, volume: 0, has_news: true,
      newest_headline_at: null, catalyst_headline: 'Guidance up', catalyst_url: null, catalyst_source: 'GlobeNewswire',
    };
    expect(tabContextFor('QNME', rows({ catalysts: [catalyst] })).catalyst).toBe('PR');
    expect(tabContextFor('QNME', rows({ catalysts: [{ ...catalyst, catalyst_source: 'Benzinga' }] })).headline).toBe('Guidance up');
    expect(tabContextFor('QNME', rows({ catalysts: [{ ...catalyst, catalyst_source: 'Benzinga' }] })).catalyst).toBe('NEWS');
    expect(tabContextFor('X', rows({ gappers: [row('X', { has_news: true })] })).catalyst).toBe('NEWS');
  });
});

describe('formatting', () => {
  it('signs and rounds the gap like the design', () => {
    expect(formatSignedPct(131.2)).toBe('+131%');
    expect(formatSignedPct(14.62)).toBe('+14.6%');
    expect(formatSignedPct(-5.4)).toBe('−5.4%');
    expect(formatSignedPct(0)).toBe('0.0%');
    expect(formatSignedPct(null)).toBe('');
    expect(pctTone(3)).toBe('up');
    expect(pctTone(-3)).toBe('down');
    expect(pctTone(null)).toBe('flat');
  });

  it('collapses a chip to its first letter', () => {
    expect(catalystInitial('guidance')).toBe('G');
  });
});
