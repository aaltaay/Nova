import { describe, expect, it } from 'vitest';
import type { IndicatorBar } from '../chartIndicators';
import { TOP_NINE_CHART_MINUTES } from './topNineConstants';
import { topNineChartGeometry } from './topNineChartGeometry';

/** ET wall-clock seconds for 2026-10-16 hh:mm (the chart's time encoding). */
function et(hh: number, mm: number): number {
  return Date.UTC(2026, 9, 16, hh, mm) / 1000;
}

function bar(hh: number, mm: number, close: number): IndicatorBar {
  return { time: et(hh, mm), open: close - 0.01, high: close + 0.02, low: close - 0.03, close, volume: 1_000 };
}

const BOX = { width: 621, height: 238 };

describe('topNineChartGeometry', () => {
  it('draws only the last 90 minutes up to the newest bar', () => {
    const bars: IndicatorBar[] = [];
    for (let m = 0; m < 200; m += 1) bars.push(bar(7 + Math.floor(m / 60), m % 60, 1 + m / 1000));
    const geo = topNineChartGeometry(bars, [], null, BOX)!;
    expect(geo.candles).toHaveLength(TOP_NINE_CHART_MINUTES);
    // 07:00 + 200 bars ends at 10:19: the window is 08:50-10:19.
    expect(geo.timeTicks.map((t) => t.label)).toEqual(['09:00', '09:30', '10:00']);
    expect(geo.last?.label).toBe('1.20'); // two places from $1 up, four below, like the desk
  });

  it('leaves a minute with no trade empty and breaks VWAP across a long hole', () => {
    const bars = [bar(9, 0, 2), bar(9, 1, 2.1), bar(9, 30, 2.2), bar(9, 31, 2.3)];
    const vwap = bars.map((b) => ({ time: b.time, value: 2.1 }));
    const geo = topNineChartGeometry(bars, vwap, 2.35, BOX)!;
    expect(geo.candles).toHaveLength(4);
    expect(geo.vwap).toHaveLength(2);
    // The tag is the board's price, and no axis label sits under it.
    expect(geo.last?.label).toBe('2.35');
    for (const t of geo.priceTicks) expect(Math.abs(t.y - geo.last!.y)).toBeGreaterThan(15);
  });

  it('ends every tile at the board minute, so a halted stock lines up with the others', () => {
    const bars = [bar(9, 40, 35), bar(9, 50, 35)];
    const geo = topNineChartGeometry(bars, [], 35, BOX, et(10, 13))!;
    expect(geo.timeTicks.map((t) => t.label)).toEqual(['09:00', '09:30', '10:00']);
    expect(geo.candles.every((c) => c.x < geo.plotRight)).toBe(true);
    // The newest candle sits 23 minutes before the right edge, not at it.
    expect(geo.plotRight - geo.candles[1].x).toBeGreaterThan(100);
  });

  it('answers null with no bars or no room', () => {
    expect(topNineChartGeometry([], [], 1, BOX)).toBeNull();
    expect(topNineChartGeometry([bar(9, 0, 1)], [], 1, { width: 40, height: 20 })).toBeNull();
  });
});
