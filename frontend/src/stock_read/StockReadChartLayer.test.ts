import { describe, expect, it, vi } from 'vitest';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { buildSeriesTimeIndex } from '../chart';
import { watchOperatorView } from '../chart/operatorView';
import { etChartSeconds } from '../tickerChartData';
import type { PriceLineSpec } from './chartShapes';
import { lineWords, runMarks } from './paneScene';
import { frameFrom, roomAtLiveEdge } from './StockReadChartLayer';
import type { RunDay } from './types';

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

  it('leaves a view the operator zoomed at the live edge exactly where they put it (2026-10-06)', () => {
    const listeners = new Map<string, () => void>();
    let onRange: (() => void) | null = null;
    const setVisibleLogicalRange = vi.fn();
    const chart = {
      chartElement: () => ({
        addEventListener: (type: string, fn: () => void) => listeners.set(type, fn),
        removeEventListener: vi.fn(),
        ownerDocument: { defaultView: null },
      }),
      timeScale: () => ({
        getVisibleLogicalRange: () => ({ from: 260, to: 280 }),
        setVisibleLogicalRange,
        subscribeVisibleLogicalRangeChange: (h: () => void) => {
          onRange = h;
        },
        unsubscribeVisibleLogicalRangeChange: vi.fn(),
      }),
    } as unknown as IChartApi;
    const stop = watchOperatorView(chart, () => 0);
    listeners.get('wheel')?.();
    (onRange as (() => void) | null)?.();
    roomAtLiveEdge(chart, 281);
    expect(setVisibleLogicalRange).not.toHaveBeenCalled();
    stop();
  });
});

describe("runMarks (the Full Day pane's +40% runs)", () => {
  const day = (date: string, over: Partial<RunDay> = {}): RunDay => ({
    date, prior_close: 1, high: 2, close: 1.5, run_pct: 0.5, close_pct: 0.5, today: false, ...over,
  });
  it("puts each run over its candle's high, today's first where labels crowd and then the biggest", () => {
    const index = buildSeriesTimeIndex(['2026-09-28', '2026-09-29', '2026-09-30'] as Time[]);
    const marks = runMarks([day('2026-09-28', { run_pct: 1.07, high: 9.5 }), day('2026-09-29', { run_pct: 0.43 }),
      day('2026-09-30', { today: true, run_pct: 0.56 }), day('2026-01-02')], index);
    expect(marks.map(m => m.label)).toEqual(['+107%', '+43%', 'today +56%']);
    expect(marks[0]).toMatchObject({ t: '2026-09-28', price: 9.5 });
    expect(marks[2].rank).toBeGreaterThan(marks[0].rank);
    expect(marks[0].rank).toBeGreaterThan(marks[1].rank);
  });
});

describe("lineWords (the plan's lines name themselves in the edge column)", () => {
  it('takes the names of the lines with an axis label; the axis keeps their prices', () => {
    const line = (id: string, title: string, axisLabel = true): PriceLineSpec =>
      ({ id, price: 4.75, color: '#0a84ff', width: 2, style: 'dashed', title, axisLabel });
    const words = lineWords([line('entry', 'ENTRY · plan'), line('thin', ''), line('quiet', 'STOP', false)]);
    expect(words).toEqual([expect.objectContaining({ id: 'line:entry', text: 'ENTRY · plan', price: 4.75, series: null })]);
  });
});
