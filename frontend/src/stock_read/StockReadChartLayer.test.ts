import { describe, expect, it, vi } from 'vitest';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { etChartSeconds } from '../tickerChartData';
import { frameFrom, roomAtLiveEdge } from './StockReadChartLayer';

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

function viewAt(range: { from: number; to: number } | null) {
  const setVisibleLogicalRange = vi.fn();
  const applyOptions = vi.fn();
  const chart = {
    timeScale: () => ({ getVisibleLogicalRange: () => range, setVisibleLogicalRange, applyOptions }),
  } as unknown as IChartApi;
  return { chart, setVisibleLogicalRange, applyOptions };
}

describe('roomAtLiveEdge (the plan zones never move a view the operator moved)', () => {
  it('slides a view that follows the last candle so the zones have room, keeping its zoom', () => {
    const { chart, setVisibleLogicalRange, applyOptions } = viewAt({ from: 230, to: 280 });
    roomAtLiveEdge(chart, 281);
    expect(setVisibleLogicalRange).toHaveBeenCalledWith({ from: 242, to: 292 });
    // rightOffset is the scroll position: setting it snapped the pane to the live edge.
    expect(applyOptions).not.toHaveBeenCalled();
  });

  it('leaves a view panned back in the day where it is', () => {
    const { chart, setVisibleLogicalRange } = viewAt({ from: 20, to: 80 });
    roomAtLiveEdge(chart, 281);
    expect(setVisibleLogicalRange).not.toHaveBeenCalled();
  });

  it('leaves a view that already has the room', () => {
    const { chart, setVisibleLogicalRange } = viewAt({ from: 240, to: 292 });
    roomAtLiveEdge(chart, 281);
    expect(setVisibleLogicalRange).not.toHaveBeenCalled();
  });
});
