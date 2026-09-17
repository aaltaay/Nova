import { describe, expect, it, vi } from 'vitest';
import type { IChartApi } from 'lightweight-charts';
import { canIncrementalBarsUpdate, type RawBar } from '../tickerChartData';
import {
  applyTimeScaleCommand,
  defaultTimeScaleCommand,
  followLogicalRange,
  isFollowingRightEdge,
  paintTimeScaleCommand,
  snapshotChartViewport,
} from './chartViewportPaint';

function bar(i: number): RawBar {
  return { t: `t${i}`, o: 1, h: 1, l: 1, c: 1, v: 1 };
}

function fakeChart(opts?: {
  logical?: { from: number; to: number } | null;
  time?: { from: number; to: number } | null;
}) {
  const fitContent = vi.fn();
  const setVisibleLogicalRange = vi.fn();
  const setVisibleRange = vi.fn();
  const getVisibleLogicalRange = vi.fn(() => opts?.logical ?? null);
  const getVisibleRange = vi.fn(() => opts?.time ?? null);
  const chart = {
    timeScale: () => ({
      fitContent,
      setVisibleLogicalRange,
      setVisibleRange,
      getVisibleLogicalRange,
      getVisibleRange,
    }),
  } as unknown as IChartApi;
  return {
    chart,
    fitContent,
    setVisibleLogicalRange,
    setVisibleRange,
    getVisibleLogicalRange,
    getVisibleRange,
  };
}

describe('10Sec live paints that force setData', () => {
  it('treats a hist-style rewrite / rolling cap as non-incremental (the jump trigger)', () => {
    const prev = [bar(0), bar(1), bar(2), bar(3)];
    const prepended = [bar(-1), ...prev];
    const rolled = [...prev.slice(1), bar(4)];
    expect(canIncrementalBarsUpdate(prev, prepended)).toBe(false);
    expect(canIncrementalBarsUpdate(prev, rolled)).toBe(false);
    expect(canIncrementalBarsUpdate(prev, [...prev.slice(0, 3), { ...bar(3), c: 2 }])).toBe(true);
  });
});

describe('paintTimeScaleCommand', () => {
  it('first 10Sec paint fits content (no pinned window)', () => {
    expect(paintTimeScaleCommand('10Sec', 1400, null)).toEqual({ kind: 'fitContent' });
    expect(defaultTimeScaleCommand('10Sec', 1400)).toEqual({ kind: 'fitContent' });
  });

  it('first 1Min paint with a long series uses the pinned window, not fitContent', () => {
    expect(paintTimeScaleCommand('1Min', 900, null)).toEqual({
      kind: 'setVisibleLogicalRange',
      range: { from: 400, to: 899 },
    });
  });

  it('never fitContents a later 10Sec paint after the operator zoomed', () => {
    const command = paintTimeScaleCommand('10Sec', 1500, {
      logical: { from: 1363, to: 1399 },
      time: { from: 1_000, to: 1_360 },
      barCount: 1400,
    });
    expect(command?.kind).not.toBe('fitContent');
  });

  it('keeps the zoom span and advances the right edge when following live', () => {
    expect(isFollowingRightEdge({ from: 1363, to: 1399 }, 1400)).toBe(true);
    expect(followLogicalRange({ from: 1363, to: 1399 }, 1500)).toEqual({
      from: 1463,
      to: 1499,
    });
    expect(
      paintTimeScaleCommand('10Sec', 1500, {
        logical: { from: 1363, to: 1399 },
        time: { from: 1_000, to: 1_360 },
        barCount: 1400,
      }),
    ).toEqual({
      kind: 'setVisibleLogicalRange',
      range: { from: 1463, to: 1499 },
    });
  });

  it('restores the time window when the operator panned away from the tip', () => {
    const time = { from: 200, to: 560 };
    expect(isFollowingRightEdge({ from: 20, to: 56 }, 1400)).toBe(false);
    expect(
      paintTimeScaleCommand('10Sec', 1500, {
        logical: { from: 20, to: 56 },
        time,
        barCount: 1400,
      }),
    ).toEqual({ kind: 'setVisibleRange', range: time });
  });

  it('does not invent a fitContent fallback when the snapshot is empty', () => {
    expect(
      paintTimeScaleCommand('10Sec', 1500, {
        logical: null,
        time: null,
        barCount: 1400,
      }),
    ).toBeNull();
  });
});

describe('applyTimeScaleCommand + snapshot', () => {
  it('applies follow without calling fitContent', () => {
    const { chart, fitContent, setVisibleLogicalRange } = fakeChart({
      logical: { from: 1363, to: 1399 },
      time: { from: 1_000, to: 1_360 },
    });
    const snapshot = snapshotChartViewport(chart, 1400);
    expect(snapshot?.logical).toEqual({ from: 1363, to: 1399 });
    applyTimeScaleCommand(
      chart,
      paintTimeScaleCommand('10Sec', 1500, snapshot),
    );
    expect(fitContent).not.toHaveBeenCalled();
    expect(setVisibleLogicalRange).toHaveBeenCalledWith({ from: 1463, to: 1499 });
  });

  it('first 10Sec paint still fitContents', () => {
    const { chart, fitContent } = fakeChart();
    applyTimeScaleCommand(chart, paintTimeScaleCommand('10Sec', 1400, null));
    expect(fitContent).toHaveBeenCalledTimes(1);
  });

  it('is a no-op without a chart or command', () => {
    expect(() => applyTimeScaleCommand(null, { kind: 'fitContent' })).not.toThrow();
    const { chart, fitContent } = fakeChart();
    applyTimeScaleCommand(chart, null);
    expect(fitContent).not.toHaveBeenCalled();
  });
});
