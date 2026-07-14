import { describe, expect, it } from 'vitest';
import { computeMacdPane, computeRsiPane, rawBarsToIndicatorBars, toggleIndicator } from './chartIndicators';
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

  it('computes finite RSI points via lightweight-charts-indicators', () => {
    const bars = rawBarsToIndicatorBars(makeBars(40), '1Min');
    const { rsi } = computeRsiPane(bars);
    expect(rsi.length).toBeGreaterThan(0);
    expect(rsi.every(p => Number.isFinite(p.value))).toBe(true);
  });

  it('computes MACD histogram + lines via lightweight-charts-indicators', () => {
    const bars = rawBarsToIndicatorBars(makeBars(50), '1Min');
    const { histogram, macd, signal } = computeMacdPane(bars);
    expect(histogram.length).toBeGreaterThan(0);
    expect(macd.length).toBeGreaterThan(0);
    expect(signal.length).toBeGreaterThan(0);
  });

  it('toggles indicator ids without duplicates', () => {
    expect(toggleIndicator([], 'rsi')).toEqual(['rsi']);
    expect(toggleIndicator(['rsi'], 'macd')).toEqual(['rsi', 'macd']);
    expect(toggleIndicator(['rsi', 'macd'], 'rsi')).toEqual(['macd']);
  });
});
