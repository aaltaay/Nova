/** @vitest-environment jsdom */
import { expect, it } from 'vitest';
import { historicalTapeFeed } from './HistoricalTimeSales';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

const snapshot: HistoricalSnapshot = {
  active: true, symbol: 'SPY', source: 'trades', as_of: '2026-09-18T08:41:16Z',
  last: 763, volume: 600,
  prints: [
    { time: '2026-09-18T08:41:00Z', price: 763, size: 100, exchange: 'FINRA', conditions: 'O', unreported: true },
    { time: '2026-09-18T08:39:00Z', price: 762, size: 500, exchange: 'ARCA' },
  ],
};

it('preserves reached print order, metadata and unreported flags without inventing quotes or aggressor sides', () => {
  const feed = historicalTapeFeed(snapshot);
  expect(feed).toEqual({ connected: true, error: null, prints: [
    { symbol: 'SPY', time: '2026-09-18T08:41:00Z', price: 763, size: 100, exchange: 'FINRA',
      conditions: 'O', unreported: true, side: 'unknown', bid: null, ask: null },
    { symbol: 'SPY', time: '2026-09-18T08:39:00Z', price: 762, size: 500, exchange: 'ARCA',
      conditions: '', unreported: false, side: 'unknown', bid: null, ask: null },
  ] });
});

it('keeps a completed-candles snapshot empty instead of manufacturing tape prints', () => {
  expect(historicalTapeFeed({ ...snapshot, source: 'completed_bars', prints: [] }).prints).toEqual([]);
});

it('passes snapshot errors through to the shared tape view', () => {
  expect(historicalTapeFeed({ ...snapshot, prints: [], error: 'Replay unavailable' })).toEqual({
    prints: [], connected: true, error: 'Replay unavailable',
  });
});
