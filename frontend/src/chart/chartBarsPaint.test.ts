import { describe, expect, it, vi } from 'vitest';
import type { RawBar } from '../tickerChartData';
import { paintBars, shouldSkipIndicatorBarsCommit } from './chartBarsPaint';

function bar(i: number, extra: Partial<RawBar> = {}): RawBar {
  const sec = String(i).padStart(2, '0');
  return {
    t: `2026-09-18T13:00:${sec}.000Z`,
    o: 10,
    h: 10,
    l: 10,
    c: 10,
    v: 100,
    ...extra,
  };
}

function seriesStub() {
  return {
    update: vi.fn(),
    setData: vi.fn(),
  };
}

describe('shouldSkipIndicatorBarsCommit', () => {
  it('skips a same-length tip-only 10Sec update', () => {
    const prev = [bar(0), bar(10)];
    const next = [bar(0), bar(10, { c: 11, h: 11, v: 140 })];
    expect(shouldSkipIndicatorBarsCommit(prev, next)).toBe(true);
  });

  it('rebuilds indicators when a new 10Sec bucket appends', () => {
    const prev = [bar(0), bar(10)];
    const next = [bar(0), bar(10), bar(20)];
    expect(shouldSkipIndicatorBarsCommit(prev, next)).toBe(false);
  });

  it('rebuilds when an older bar is rewritten', () => {
    const prev = [bar(0), bar(10)];
    const next = [bar(0, { c: 9 }), bar(10)];
    expect(shouldSkipIndicatorBarsCommit(prev, next)).toBe(false);
  });
});

describe('paintBars tip-only path', () => {
  it('calls series.update and skips setData + indicator rebuild on tip change', () => {
    const candle = seriesStub();
    const vol = seriesStub();
    const prev = [bar(0), bar(10)];
    const next = [bar(0), bar(10, { c: 11, h: 11, v: 140 })];
    const result = paintBars(
      next,
      '10Sec',
      { current: candle as never },
      { current: vol as never },
      { current: null },
      { current: null },
      prev,
      { current: 0 },
    );
    expect(candle.update).toHaveBeenCalledTimes(1);
    expect(vol.update).toHaveBeenCalledTimes(1);
    expect(candle.setData).not.toHaveBeenCalled();
    expect(vol.setData).not.toHaveBeenCalled();
    expect(result.tipOnly).toBe(true);
    expect(result.skipIndicatorCommit).toBe(true);
    expect(result.indicators).toEqual([]);
  });

  it('uses setData when history is rewritten', () => {
    const candle = seriesStub();
    const vol = seriesStub();
    const prev = [bar(0), bar(10)];
    const next = [bar(0, { c: 9 }), bar(10)];
    const result = paintBars(
      next,
      '10Sec',
      { current: candle as never },
      { current: vol as never },
      { current: null },
      { current: null },
      prev,
      { current: 0 },
    );
    expect(candle.setData).toHaveBeenCalled();
    expect(candle.update).not.toHaveBeenCalled();
    expect(result.skipIndicatorCommit).toBe(false);
    expect(result.indicators.length).toBe(2);
  });
});
