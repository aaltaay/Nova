import { describe, expect, it, vi } from 'vitest';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { etChartSeconds } from '../tickerChartData';
import { frameFrom } from './StockReadChartLayer';

const OPEN = Date.parse('2026-09-25T08:00:00Z') / 1000; // 04:00 ET

function pane(barTimes: () => number[]) {
  const setVisibleLogicalRange = vi.fn();
  const chart = { timeScale: () => ({ setVisibleLogicalRange }) } as unknown as IChartApi;
  const series = {
    data: () => barTimes().map(t => ({ time: etChartSeconds(t * 1000) as Time })),
  } as unknown as ISeriesApi<'Candlestick'>;
  return { chart, series, setVisibleLogicalRange };
}

function minutes(fromSec: number, count: number): number[] {
  return Array.from({ length: count }, (_, i) => fromSec + i * 60);
}

describe('frameFrom', () => {
  it('frames from the candles the pane holds when it frames, not an earlier set', () => {
    // A day of history first, then a pane that holds more bars (a longer store read).
    let held = minutes(OPEN, 270);
    const { chart, series, setVisibleLogicalRange } = pane(() => held);
    const legSec = OPEN + 240 * 60; // 08:00 ET

    expect(frameFrom(chart, series, legSec)).toBe(true);
    expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 228, to: 281 });

    held = [...minutes(OPEN - 300 * 60, 300), ...minutes(OPEN, 270)];
    frameFrom(chart, series, legSec);
    expect(setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 528, to: 581 });
  });

  it('frames nothing while the pane holds no candles', () => {
    const { chart, series, setVisibleLogicalRange } = pane(() => []);
    expect(frameFrom(chart, series, OPEN)).toBe(false);
    expect(setVisibleLogicalRange).not.toHaveBeenCalled();
  });
});
