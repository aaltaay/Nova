import { describe, expect, it } from 'vitest';
import type { CandlestickData, Time } from 'lightweight-charts';
import {
  canIncrementalBarsUpdate,
  shouldFitContentOnHistoryPaint,
  timeScaleRangeForSeries,
  formatCoverageClockEt,
  clearEtOffsetCacheForTests,
  etCalendarDateString,
  isOutOfOrderTrade,
  isSubMinuteTimeframe,
  rawBarsToSeries,
  timeframeSeconds,
  tradeBucket,
  type RawBar,
} from './tickerChartData';

const candle = (time: number): CandlestickData<Time> => ({
  time: time as Time,
  open: 1,
  high: 1,
  low: 1,
  close: 1,
});

describe('ticker chart trade ordering', () => {
  it('rejects a trade bucket older than the latest REST candle', () => {
    expect(isOutOfOrderTrade(candle(1_000), 999 as Time)).toBe(true);
  });

  it('accepts same-bucket and newer trades', () => {
    expect(isOutOfOrderTrade(candle(1_000), 1_000 as Time)).toBe(false);
    expect(isOutOfOrderTrade(candle(1_000), 1_001 as Time)).toBe(false);
  });

  it('rejects an invalid trade timestamp before it reaches the chart library', () => {
    expect(tradeBucket('not-a-date', '1Min')).toBeNull();
  });

  it('parses Sec / Min / Hour bucket sizes', () => {
    expect(timeframeSeconds('10Sec')).toBe(10);
    expect(timeframeSeconds('1Min')).toBe(60);
    expect(timeframeSeconds('1Hour')).toBe(3600);
    expect(isSubMinuteTimeframe('10Sec')).toBe(true);
    expect(isSubMinuteTimeframe('1Min')).toBe(false);
  });

  it('buckets 10Sec trades on 10-second boundaries (not 60s)', () => {
    clearEtOffsetCacheForTests();
    // 14:00:05Z and 14:00:09Z share a 10s bucket; 14:00:10Z rolls over.
    const a = tradeBucket('2026-07-29T14:00:05Z', '10Sec');
    const b = tradeBucket('2026-07-29T14:00:09Z', '10Sec');
    const c = tradeBucket('2026-07-29T14:00:10Z', '10Sec');
    expect(a).not.toBeNull();
    expect(a).toBe(b);
    expect(c).not.toBe(a);
    if (typeof a === 'number' && typeof c === 'number') {
      expect(c - a).toBe(10);
    }
  });

  it('buckets 1Day trades as ET calendar YYYY-MM-DD (matches daily series times)', () => {
    clearEtOffsetCacheForTests();
    const bucket = tradeBucket('2026-07-29T21:30:00Z', '1Day');
    expect(bucket).toBe(etCalendarDateString(new Date('2026-07-29T21:30:00Z')));
    expect(typeof bucket).toBe('string');
  });
});

describe('ticker chart bar conversion', () => {
  it('builds candles and volumes in one pass', () => {
    clearEtOffsetCacheForTests();
    const bars: RawBar[] = [
      { t: '2026-07-29T14:00:00Z', o: 1, h: 2, l: 0.5, c: 1.5, v: 10 },
      { t: '2026-07-29T14:01:00Z', o: 1.5, h: 2, l: 1, c: 1.2, v: 20 },
    ];
    const { candles, volumes } = rawBarsToSeries(bars, '1Min');
    expect(candles).toHaveLength(2);
    expect(volumes).toHaveLength(2);
    expect(candles[0].time).toBe(volumes[0].time);
  });

  it('allows incremental update only when the tip bar changes or appends', () => {
    const prev: RawBar[] = [
      { t: 'a', o: 1, h: 1, l: 1, c: 1, v: 1 },
      { t: 'b', o: 1, h: 1, l: 1, c: 1, v: 1 },
      { t: 'c', o: 1, h: 1, l: 1, c: 1, v: 1 },
      { t: 'd', o: 1, h: 1, l: 1, c: 1, v: 1 },
    ];
    const tipChanged = [...prev.slice(0, 3), { t: 'd', o: 1, h: 2, l: 1, c: 1.5, v: 9 }];
    const appended = [...prev, { t: 'e', o: 1, h: 1, l: 1, c: 1, v: 1 }];
    expect(canIncrementalBarsUpdate(prev, tipChanged)).toBe(true);
    expect(canIncrementalBarsUpdate(prev, appended)).toBe(true);
    expect(canIncrementalBarsUpdate(prev, [{ t: 'z', o: 1, h: 1, l: 1, c: 1, v: 1 }])).toBe(false);
    // Rewriting an older bar must force a full setData.
    const olderRewritten = [
      ...prev.slice(0, 2),
      { t: 'c', o: 9, h: 9, l: 9, c: 9, v: 9 },
      prev[3],
    ];
    expect(canIncrementalBarsUpdate(prev, olderRewritten)).toBe(false);
  });

  it('uses a session-sized window for 5Min and fits short 1Min series', () => {
    expect(timeScaleRangeForSeries('1Min', 400)).toBeNull();
    expect(timeScaleRangeForSeries('10Sec', 1400)).toBeNull();
    expect(timeScaleRangeForSeries('5Min', 50)).toBeNull();
    expect(timeScaleRangeForSeries('5Min', 500)).toEqual({ from: 404, to: 499 });
    expect(timeScaleRangeForSeries('1Day', 500)).toEqual({ from: 320, to: 499 });
  });

  it('formats coverage as_of in ET instead of slicing UTC', () => {
    expect(formatCoverageClockEt('2026-08-18T16:11:00Z')).toBe('12:11');
    expect(formatCoverageClockEt(null)).toBeNull();
  });

  it('fits the first historical series and a stub-to-full jump', () => {
    const stub: RawBar[] = [
      { t: 'now', o: 1, h: 1, l: 1, c: 1, v: 1 },
    ];
    const history = Array.from({ length: 40 }, (_, i) => ({
      t: `t${i}`,
      o: 1,
      h: 1,
      l: 1,
      c: 1,
      v: 1,
    }));
    expect(shouldFitContentOnHistoryPaint(null, history)).toBe(true);
    expect(shouldFitContentOnHistoryPaint([], history)).toBe(true);
    expect(shouldFitContentOnHistoryPaint(stub, history)).toBe(true);
    expect(shouldFitContentOnHistoryPaint(history, history)).toBe(false);
    const tipUpdate = [
      ...history.slice(0, -1),
      { t: 't39', o: 1, h: 2, l: 1, c: 1.5, v: 9 },
    ];
    expect(shouldFitContentOnHistoryPaint(history, tipUpdate)).toBe(false);
    expect(shouldFitContentOnHistoryPaint(history, [...history, stub[0]])).toBe(false);
    expect(shouldFitContentOnHistoryPaint(history, [])).toBe(false);
  });
});
