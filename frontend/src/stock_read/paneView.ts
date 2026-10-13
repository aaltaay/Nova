/**
 * Where the stock read moves a chart pane's view (ADR 036): framing a setup, and room right of the last candle for the
 * plan's zones or a setup's strategy box at the live edge. A view the operator zoomed or panned is theirs and never
 * moved here (`chart/operatorView.ts`). Each move is made after the pane's own paint has applied its view again
 * (`afterPaintSettles`): made before, the paint put it back and it was never made again, so the 1-minute strategy box
 * sat squeezed against the right edge on some loads (operator ask 2026-10-13).
 */
import { useEffect, useRef } from 'react';
import type { ISeriesApi } from 'lightweight-charts';
import {
  afterPaintSettles,
  buildSeriesTimeIndex,
  isFollowingRightEdge,
  operatorOwnsView,
  type ChartPaneOverlayProps,
  type SeriesTimeIndex,
} from '../chart';
import { etChartSeconds } from '../tickerChartData';

/** Room right of the last candle for the plan's zones on the 1-minute pane. */
const PLAN_RIGHT_OFFSET_BARS = 12;
/** Candles shown before a setup begins when the pane frames it, and the fewest it shows. */
const FRAME_PAD_BARS = 12;
const FRAME_MIN_BARS = 40;

export function seriesIndex(series: ISeriesApi<'Candlestick'> | null): SeriesTimeIndex {
  return buildSeriesTimeIndex(series ? series.data().map(d => d.time) : []);
}

/**
 * Show the pane's candles from a little before `fromSec` to its last one and the plan's room after it.
 * The range is bar positions, so they are read from the candles the pane holds now: an index kept from
 * an earlier render counts other bars once the series has changed under it.
 */
export function frameFrom(
  chart: ChartPaneOverlayProps['chart'],
  series: ISeriesApi<'Candlestick'> | null,
  fromSec: number,
): boolean {
  const index = seriesIndex(series);
  const n = index.canonical.length;
  if (!chart || n === 0) return false;
  const target = etChartSeconds(fromSec * 1000);
  let i = index.canonical.findIndex(t => t >= target);
  if (i < 0) i = n - 1;
  const from = Math.max(0, Math.min(i - FRAME_PAD_BARS, n - 1 - FRAME_MIN_BARS));
  chart.timeScale().setVisibleLogicalRange({ from, to: n - 1 + PLAN_RIGHT_OFFSET_BARS });
  return true;
}

/** Slide a view that follows the live edge so the plan's zones have room past the last candle -- at least `minPx` of
 * it (a setup's strategy box) -- a view the operator zoomed or panned stays exactly where they put it, even at the live
 * edge. */
export function roomAtLiveEdge(chart: NonNullable<ChartPaneOverlayProps['chart']>, barCount: number, minPx = 0): void {
  if (operatorOwnsView(chart)) return;
  const last = barCount - 1;
  try {
    const ts = chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    const spacing = minPx > 0 ? ts.options().barSpacing : 0;
    const room = spacing > 0 ? Math.max(PLAN_RIGHT_OFFSET_BARS, Math.ceil(minPx / spacing)) : PLAN_RIGHT_OFFSET_BARS;
    if (!range || !isFollowingRightEdge(range, barCount) || range.to >= last + room) return;
    const shift = last + room - range.to;
    ts.setVisibleLogicalRange({ from: range.from + shift, to: range.to + shift });
  } catch {
    /* the chart is gone */
  }
}

/**
 * Room for the plan's zones (or a setup's strategy box, `minPx` of it) right of the last candle when they appear, once
 * each time, and only for a view that follows the live edge. The time scale's rightOffset used to do this: it is the
 * scroll position, so the pane jumped to the live edge whenever the zones came or went -- a buy, a sale, a tab shown
 * again.
 */
export function useRoomAtLiveEdge(chart: ChartPaneOverlayProps['chart'], series: ISeriesApi<'Candlestick'> | null,
  zones: boolean, minPx: number, barsRevision: number): void {
  const pending = useRef(true);
  useEffect(() => {
    if (!zones) {
      pending.current = true;
      return undefined;
    }
    if (!chart || !series || !pending.current) return undefined;
    return afterPaintSettles(() => {
      const n = series.data().length;
      if (n === 0 || !pending.current) return;
      pending.current = false;
      roomAtLiveEdge(chart, n, minPx);
    });
  }, [chart, series, zones, minPx, barsRevision]);
}
