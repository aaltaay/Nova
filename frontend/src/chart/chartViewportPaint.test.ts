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
  timeRangesOverlap,
  tipLogicalRange,
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
    expect(followLogicalRange({ from: 1363, to: 1399 }, 1500, 1400)).toEqual({
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

  it('preserves a right margin the operator panned open (the yank regression)', () => {
    // Last bar mid-pane: `to` runs 50 bars past the tip into the whitespace.
    const panned = { from: 1363, to: 1450 };
    expect(isFollowingRightEdge(panned, 1400)).toBe(true);
    // 100 bars arrive. Both invariants hold: the margin past the tip and the
    // zoom span survive. Clamping `to` to the tip broke the first one.
    const next = followLogicalRange(panned, 1500, 1400);
    expect(next).toEqual({ from: 1463, to: 1550 });
    expect(next.to - (1500 - 1)).toBe(panned.to - (1400 - 1));
    expect(next.to - next.from).toBe(panned.to - panned.from);
  });

  it('keeps the margin through a prepend and a rolling trim', () => {
    const panned = { from: 40, to: 130 };
    // Prepend: every index shifted right by one, so the window shifts with it.
    expect(followLogicalRange(panned, 101, 100)).toEqual({ from: 41, to: 131 });
    // Rolling trim (same length, contents shifted left): window stays put and
    // therefore follows the new tip, margin intact.
    expect(followLogicalRange(panned, 100, 100)).toEqual(panned);
  });

  it('paintTimeScaleCommand routes a panned-open margin through follow', () => {
    expect(
      paintTimeScaleCommand('10Sec', 1500, {
        logical: { from: 1363, to: 1450 },
        time: { from: 1_000, to: 1_360 },
        barCount: 1400,
      }),
    ).toEqual({
      kind: 'setVisibleLogicalRange',
      range: { from: 1463, to: 1550 },
    });
  });

  it('restores a panned-away window that the new bars still hold (venue switch)', () => {
    const time = { from: 200, to: 560 };
    expect(
      paintTimeScaleCommand('1Min', 300, {
        logical: { from: 20, to: 56 },
        time,
        barCount: 700,
      }, { from: 100, to: 9_000 }),
    ).toEqual({ kind: 'setVisibleRange', range: time });
  });

  it('keeps the zoom at the tip when the new bars do not hold the window (another day)', () => {
    // Panned to a live window, then Sim loaded a replay of another day: the
    // window would paint an empty pane. Same span, right edge on the newest bar.
    expect(
      paintTimeScaleCommand('1Min', 300, {
        logical: { from: 20, to: 56 },
        time: { from: 200, to: 560 },
        barCount: 700,
      }, { from: 90_000, to: 99_000 }),
    ).toEqual({ kind: 'setVisibleLogicalRange', range: tipLogicalRange(36, 300) });
    expect(tipLogicalRange(36, 300)).toEqual({ from: 263, to: 299 });
  });

  it('compares daily business-day windows too', () => {
    expect(timeRangesOverlap(
      { from: '2026-09-01', to: '2026-09-10' } as never,
      { from: '2026-09-09', to: '2026-09-23' } as never,
    )).toBe(true);
    expect(timeRangesOverlap(
      { from: '2026-08-01', to: '2026-08-10' } as never,
      { from: '2026-09-09', to: '2026-09-23' } as never,
    )).toBe(false);
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

  it('a zero-bar snapshot is null, which is why the empty gap needs an override', () => {
    const { chart } = fakeChart({ logical: { from: 1363, to: 1450 }, time: null });
    // This is the poisoning path: after an empty refresh clears the series the
    // caller holds `prevBars === []`, and snapshotting 0 bars yields null ->
    // "first paint" -> fitContent. useChartBars must capture before the wipe.
    expect(snapshotChartViewport(chart, 0)).toBeNull();
    expect(snapshotChartViewport(chart, 1400)?.logical).toEqual({ from: 1363, to: 1450 });
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
