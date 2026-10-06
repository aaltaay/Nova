/** @vitest-environment jsdom */
import { expect, it } from 'vitest';
import { historicalTapeFeed, tapeSidesTitle } from './HistoricalTimeSales';
import {
  SIM_REPLAY_TAPE_SIDES_NBBO, SIM_REPLAY_TAPE_SIDES_NBBO_MISSING, SIM_REPLAY_TAPE_SIDES_NONE,
  SIM_REPLAY_TAPE_SIDES_RECORDED,
} from './simConstants';
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
      conditions: 'O', unreported: true, side: 'unknown', bid: null, ask: null, setsPrice: true },
    { symbol: 'SPY', time: '2026-09-18T08:39:00Z', price: 762, size: 500, exchange: 'ARCA',
      conditions: '', unreported: false, side: 'unknown', bid: null, ask: null, setsPrice: true },
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

it('shows a real side exactly where the local recording decided one, and nothing elsewhere', () => {
  const feed = historicalTapeFeed({ ...snapshot, sides_recorded: 1, prints: [
    { time: '2026-09-18T14:00:01Z', price: 5.02, size: 100, exchange: 'NSDQ',
      side: 'ask', bid: 5.0, ask: 5.02, side_source: 'recorded_book' },
    { time: '2026-09-18T14:00:00Z', price: 5.01, size: 100, exchange: 'ARCA', side: null },
  ] });
  expect(feed.prints.map(p => [p.side, p.bid, p.ask])).toEqual([['ask', 5.0, 5.02], ['unknown', null, null]]);
});

it('dims a Massive print that moves no price and colours it from the NBBO, saying so (ADR 046)', () => {
  const massive: HistoricalSnapshot = {
    ...snapshot, quote_status: 'complete', sides_nbbo: 1,
    selection: { symbol: 'SPY', date: '2026-09-18', start: '09:30', end: '10:00', coverage_through: 0, source: 'massive' },
    prints: [
      { time: '2026-09-18T13:30:00.250Z', price: 9.5, size: 10, exchange: 'NASDAQ', conditions: '37', sets_price: false },
      { time: '2026-09-18T13:30:00.100Z', price: 10, size: 100, exchange: 'NASDAQ',
        side: 'ask', bid: 9.98, ask: 10, side_source: 'nbbo' },
    ],
  };
  const feed = historicalTapeFeed(massive);
  expect(feed.prints.map(p => [p.setsPrice, p.side])).toEqual([[false, 'unknown'], [true, 'ask']]);
  expect(tapeSidesTitle(massive)).toBe(SIM_REPLAY_TAPE_SIDES_NBBO);
  expect(tapeSidesTitle({ ...massive, quote_status: 'not_downloaded' })).toBe(SIM_REPLAY_TAPE_SIDES_NBBO_MISSING);
  expect(tapeSidesTitle(snapshot)).toBe(SIM_REPLAY_TAPE_SIDES_NONE);
  expect(tapeSidesTitle({ ...snapshot, sides_recorded: 2 })).toBe(SIM_REPLAY_TAPE_SIDES_RECORDED);
});
