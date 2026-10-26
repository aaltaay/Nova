/**
 * @vitest-environment jsdom
 *
 * Ahead's framing (ADR 065): switched on, and on each new answer, a view that follows the live edge and is Nova's is
 * framed like the approved mockup -- about 45 candles, the 15-step zone and a margin, the word column right of it --
 * and framed again on a new pane width (the panel docking); a view the operator owns is never moved.
 */
import { act, renderHook } from '@testing-library/react';
import type { IChartApi, ISeriesApi, LogicalRange } from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { publishPaneWords } from '../chart';
import { AHEAD_FRAME_CANDLES, AHEAD_FRAME_MARGIN, AHEAD_HORIZON } from './aheadConstants';
import { aheadFrameRange, frameForAhead, hasRoom, useAheadRoom } from './useAheadRoom';

let owned = false;
let paintNow = false;
vi.mock('../chart', async (orig) => ({
  ...(await orig<typeof import('../chart')>()),
  operatorOwnsView: () => owned,
  // The switch-on frame waits for the pane's paint (left out here: these tests frame by hand); a re-frame on a new
  // width runs at once.
  afterPaintSettles: (move: () => void) => {
    if (paintNow) move();
    return () => {};
  },
}));

function fakeChart(range: LogicalRange | null, width = 800) {
  const setVisibleLogicalRange = vi.fn();
  const ts = { getVisibleLogicalRange: () => range, setVisibleLogicalRange };
  const chart = { timeScale: () => ts, paneSize: () => ({ width, height: 400 }) } as unknown as IChartApi;
  return { chart, setVisibleLogicalRange };
}

afterEach(() => {
  owned = false;
  paintNow = false;
});

describe("Ahead's frame", () => {
  it('shows about 45 candles, the 15-step zone and a margin: the zone takes about a quarter of the pane', () => {
    const r = aheadFrameRange(230, 800, 0);
    expect(r.to).toBe(230 + AHEAD_HORIZON + AHEAD_FRAME_MARGIN);
    expect(r.to - r.from).toBe(AHEAD_FRAME_CANDLES + AHEAD_HORIZON + AHEAD_FRAME_MARGIN);
    const zoneShare = AHEAD_HORIZON / (r.to - r.from);
    expect(zoneShare).toBeGreaterThan(0.2);
    expect(zoneShare).toBeLessThan(0.3);
  });

  it("leaves the stock read's word column room right of the zone, the zone's own width unchanged", () => {
    const r = aheadFrameRange(230, 800, 200);
    const span = r.to - r.from;
    const columnBars = span * (200 / 800);
    // The column's 200 px are bars past the zone's end; the candles and the zone keep their count.
    expect(r.to - columnBars).toBeCloseTo(230 + AHEAD_HORIZON + AHEAD_FRAME_MARGIN);
    expect(span - columnBars).toBeCloseTo(AHEAD_FRAME_CANDLES + AHEAD_HORIZON + AHEAD_FRAME_MARGIN);
  });

  it('frames a whole-session view that follows the live edge', () => {
    const { chart, setVisibleLogicalRange } = fakeChart({ from: 0, to: 232 } as LogicalRange);
    expect(frameForAhead(chart, 231)).toBe(true);
    expect(setVisibleLogicalRange).toHaveBeenCalledWith(aheadFrameRange(230, 800, 0));
  });

  it('counts the word column the stock read published at the edge', () => {
    const { chart, setVisibleLogicalRange } = fakeChart({ from: 0, to: 232 } as LogicalRange);
    publishPaneWords(chart, 'stock-read', [{ left: 650, top: 10, right: 795, bottom: 24 }]);
    frameForAhead(chart, 231);
    expect(setVisibleLogicalRange).toHaveBeenCalledWith(aheadFrameRange(230, 800, 150));
    publishPaneWords(chart, 'stock-read', []);
  });

  it("never moves a view the operator owns, or one that no longer follows the live edge", () => {
    owned = true;
    const mine = fakeChart({ from: 0, to: 232 } as LogicalRange);
    expect(frameForAhead(mine.chart, 231)).toBe(false);
    expect(mine.setVisibleLogicalRange).not.toHaveBeenCalled();
    owned = false;
    const back = fakeChart({ from: 0, to: 120 } as LogicalRange);
    expect(frameForAhead(back.chart, 231)).toBe(false);
    expect(back.setVisibleLogicalRange).not.toHaveBeenCalled();
  });

  it('leaves a view already framed alone', () => {
    const { chart, setVisibleLogicalRange } = fakeChart(aheadFrameRange(230, 800, 0));
    expect(frameForAhead(chart, 231)).toBe(false);
    expect(setVisibleLogicalRange).not.toHaveBeenCalled();
  });

  it('says the zone has room while two steps or more show past the newest candle', () => {
    expect(hasRoom({ from: 0, to: 12 } as LogicalRange, 10)).toBe(true);
    expect(hasRoom({ from: 0, to: 11 } as LogicalRange, 10)).toBe(false);
    expect(hasRoom(null, 10)).toBe(true);
  });

  it('frames again when the pane gets a new width (the panel docking), never a view the operator owns', () => {
    let onSize: ((w: number, h: number) => void) | null = null;
    let width = 800;
    const setVisibleLogicalRange = vi.fn();
    const ts = {
      getVisibleLogicalRange: () => ({ from: 0, to: 232 }) as LogicalRange,
      setVisibleLogicalRange,
      subscribeSizeChange: (fn: (w: number, h: number) => void) => {
        onSize = fn;
      },
      unsubscribeSizeChange: vi.fn(),
      subscribeVisibleLogicalRangeChange: vi.fn(),
      unsubscribeVisibleLogicalRangeChange: vi.fn(),
    };
    const chart = { timeScale: () => ts, paneSize: () => ({ width, height: 400 }) } as unknown as IChartApi;
    const series = { data: () => new Array(231), dataByIndex: () => null } as unknown as ISeriesApi<'Candlestick'>;
    renderHook(() => useAheadRoom(chart, series, true, 1, null));
    paintNow = true;
    width = 600;
    act(() => onSize?.(600, 400));
    expect(setVisibleLogicalRange).toHaveBeenCalledWith(aheadFrameRange(230, 600, 0));
    setVisibleLogicalRange.mockClear();
    owned = true;
    width = 800;
    act(() => onSize?.(800, 400));
    expect(setVisibleLogicalRange).not.toHaveBeenCalled();
  });
});
