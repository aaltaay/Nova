import { describe, expect, it } from 'vitest';
import {
  computeEmaLine,
  computeEmaOverlays,
  computeMacdPane,
  computeRsiPane,
  formatVwapAxisTitle,
  rawBarsToIndicatorBars,
  toggleIndicator,
  vwapAxisTitleFromLine,
  vwapWaitingTitle,
} from './chartIndicators';
import { CHART_EMA_LENGTHS } from './constants';
import type { RawBar } from './tickerChartData';

function makeBars(n: number): RawBar[] {
  const bars: RawBar[] = [];
  let price = 10;
  for (let i = 0; i < n; i++) {
    const open = price;
    const close = price + (i % 2 === 0 ? 0.2 : -0.1);
    bars.push({
      t: new Date(Date.UTC(2026, 6, 14, 14, i, 0)).toISOString(),
      o: open,
      h: Math.max(open, close) + 0.05,
      l: Math.min(open, close) - 0.05,
      c: close,
      v: 1000 + i,
    });
    price = close;
  }
  return bars;
}

describe('chartIndicators (library adapters)', () => {
  it('converts raw bars into indicator bars with numeric ET times', () => {
    const bars = rawBarsToIndicatorBars(makeBars(5), '1Min');
    expect(bars).toHaveLength(5);
    expect(bars.every(b => typeof b.time === 'number')).toBe(true);
    expect(bars[0].close).toBeTypeOf('number');
  });

  it('keeps 1Day bars (business-day strings) instead of dropping them', () => {
    const daily: RawBar[] = [
      { t: '2024-08-20T00:00:00Z', o: 10, h: 11, l: 9, c: 10.5, v: 100 },
      { t: '2024-08-21T00:00:00Z', o: 10.5, h: 12, l: 10, c: 11, v: 110 },
    ];
    const bars = rawBarsToIndicatorBars(daily, '1Day');
    expect(bars).toHaveLength(2);
    expect(bars.every(b => typeof b.time === 'number')).toBe(true);
  });

  it('computes finite RSI points via lightweight-charts-indicators', () => {
    const bars = rawBarsToIndicatorBars(makeBars(40), '1Min');
    const { rsi } = computeRsiPane(bars);
    const valued = rsi.filter(p => 'value' in p && Number.isFinite(p.value));
    expect(valued.length).toBeGreaterThan(0);
    expect(rsi).toHaveLength(bars.length);
  });

  it('keeps MACD series the same length as price bars (warmup is whitespace)', () => {
    const bars = rawBarsToIndicatorBars(makeBars(50), '1Min');
    const { histogram, macd, signal } = computeMacdPane(bars);
    expect(histogram).toHaveLength(bars.length);
    expect(macd).toHaveLength(bars.length);
    expect(signal).toHaveLength(bars.length);
    const valued = macd.filter(p => 'value' in p && Number.isFinite(p.value));
    expect(valued.length).toBeGreaterThan(0);
    expect(valued.length).toBeLessThan(bars.length);
    const histValued = histogram.filter(p => 'value' in p && Number.isFinite(p.value));
    expect(histValued.every(p => 'color' in p && typeof p.color === 'string' && p.color.length > 0)).toBe(true);
  });

  it('computes finite 9/20/50/200 EMA overlays via EMA.calculate', () => {
    const bars = rawBarsToIndicatorBars(makeBars(220), '1Min');
    const emas = computeEmaOverlays(bars);
    for (const length of CHART_EMA_LENGTHS) {
      expect(emas[length].length).toBeGreaterThan(0);
      expect(emas[length].every(p => Number.isFinite(p.value))).toBe(true);
    }
    const ema9 = computeEmaLine(bars, 9);
    expect(ema9.length).toBe(emas[9].length);
  });

  it('puts the last VWAP dollar amount in the axis title', () => {
    expect(formatVwapAxisTitle(78.524)).toBe('VWAP $78.52');
    expect(formatVwapAxisTitle(0.4)).toBe('VWAP $0.40');
    expect(vwapAxisTitleFromLine([])).toBe(vwapWaitingTitle());
    expect(vwapAxisTitleFromLine([{ time: 1, value: 79.51 }])).toBe('VWAP $79.51');
    expect(vwapAxisTitleFromLine([{ time: 1 }, { time: 2, value: 79.51 }])).toBe('VWAP $79.51');
  });

  it('marks the VWAP title partial when the source misses the session open', () => {
    expect(formatVwapAxisTitle(78.524, true)).toBe('VWAP $78.52 (partial)');
    expect(vwapAxisTitleFromLine([{ time: 1, value: 79.51 }], true))
      .toBe('VWAP $79.51 (partial)');
    expect(vwapAxisTitleFromLine([], true)).toBe(vwapWaitingTitle());
  });

  it('toggles indicator ids without duplicates', () => {
    expect(toggleIndicator([], 'rsi')).toEqual(['rsi']);
    expect(toggleIndicator(['rsi'], 'macd')).toEqual(['rsi', 'macd']);
    expect(toggleIndicator(['rsi', 'macd'], 'rsi')).toEqual(['macd']);
    expect(toggleIndicator(['emas', 'vwap'], 'emas')).toEqual(['vwap']);
  });
});
