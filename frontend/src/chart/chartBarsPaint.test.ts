import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CandlestickData, LogicalRange, Time } from 'lightweight-charts';
import type { RawBar } from '../tickerChartData';
import { afterPaintSettles, paintBars, paintFull, shouldSkipIndicatorBarsCommit } from './chartBarsPaint';

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

/** Animation frames held in a queue the test runs, in the order they were asked for. */
function frameQueue() {
  const frames = new Map<number, FrameRequestCallback>();
  let next = 0;
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    next += 1;
    frames.set(next, cb);
    return next;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
  return {
    run: () => {
      for (const [id, cb] of [...frames]) {
        frames.delete(id);
        cb(0);
      }
    },
  };
}

function viewStub() {
  let range: LogicalRange | null = null;
  const ts = {
    setVisibleLogicalRange: (r: LogicalRange) => {
      range = { from: r.from, to: r.to };
    },
    getVisibleLogicalRange: () => range,
    setVisibleRange: vi.fn(),
    fitContent: vi.fn(),
  };
  return { chart: { timeScale: () => ts }, range: () => range };
}

describe("afterPaintSettles (an overlay's move outlives the paint that applies its view again a frame later)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('puts back a move made before that frame, and keeps one made through afterPaintSettles (2026-10-13)', () => {
    const frames = frameQueue();
    const view = viewStub();
    const candles = Array.from({ length: 100 }, (_, i) => (
      { time: (i * 60) as Time, open: 1, high: 1, low: 1, close: 1 })) as CandlestickData<Time>[];
    const following = { logical: { from: 40, to: 99 } as LogicalRange, time: null, barCount: 100 };
    const paint = () => paintFull(candles, [], { current: seriesStub() as never }, { current: seriesStub() as never },
      { current: view.chart as never }, '1Min', following, { current: 0 });
    const room = { from: 52, to: 111 } as LogicalRange;

    // The 1-minute strategy box squeezed against the right edge: the room was made, then the paint's frame undid it.
    paint();
    view.chart.timeScale().setVisibleLogicalRange(room);
    frames.run();
    expect(view.range()).toEqual({ from: 40, to: 99 });

    paint();
    afterPaintSettles(() => view.chart.timeScale().setVisibleLogicalRange(room));
    frames.run();
    expect(view.range()).toEqual(room);
  });

  it('drops a move its overlay cancelled before the frame', () => {
    const frames = frameQueue();
    const move = vi.fn();
    afterPaintSettles(move)();
    frames.run();
    expect(move).not.toHaveBeenCalled();
  });
});
