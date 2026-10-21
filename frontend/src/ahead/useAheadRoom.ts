/**
 * Room for Ahead's zone right of the newest candle (ADR 065). When Ahead comes on, a view that follows the live edge
 * slides once so `AHEAD_ROOM_BARS` candles of room show after the last one (`roomAtLiveEdge`, the stock read's own
 * rule: it only ever widens, and a view the operator zoomed or panned stays exactly where they put it), plus the width
 * of the stock read's word column at the edge, which the zone stops short of. Then it tells, as the view moves,
 * whether the zone has any room on screen at all -- the scene says so in words when it has none.
 */
import { useEffect, useRef, useState } from 'react';
import { MismatchDirection, type IChartApi, type ISeriesApi, type LogicalRange } from 'lightweight-charts';
import { afterPaintSettles } from '../chart';
import { roomAtLiveEdge } from '../stock_read';
import { AHEAD_ROOM_BARS } from './aheadConstants';
import { edgeInset } from './AheadPrimitive';

/** Fewer whole steps than this past the newest candle on screen: the zone has no room. */
const ROOM_MIN_STEPS = 2;

/** The newest candle's logical index on the pane, by search (no copy of the bars). */
function lastIndex(chart: IChartApi, series: ISeriesApi<'Candlestick'>): number | null {
  const row = series.dataByIndex(Number.MAX_SAFE_INTEGER, MismatchDirection.NearestLeft);
  return row ? chart.timeScale().timeToIndex(row.time, true) : null;
}

/** Pure: does a visible range leave the zone room past the newest candle, short of `insetBars` at the edge? */
export function hasRoom(range: LogicalRange | null, last: number | null, insetBars = 0): boolean {
  if (!range || last === null) return true;
  return range.to - insetBars - last >= ROOM_MIN_STEPS;
}

/** The word column at the pane's right edge, in candles. */
function insetBars(chart: IChartApi): number {
  const spacing = chart.timeScale().options().barSpacing || 1;
  return edgeInset(chart, chart.paneSize().width) / spacing;
}

export function useAheadRoom(chart: IChartApi | null, series: ISeriesApi<'Candlestick'> | null, on: boolean,
  barsRevision: number): boolean {
  const pending = useRef(true);
  const [roomOk, setRoomOk] = useState(true);

  useEffect(() => {
    if (!on) {
      pending.current = true;
      return undefined;
    }
    if (!chart || !series || !pending.current) return undefined;
    return afterPaintSettles(() => {
      const n = series.data().length;
      if (n === 0 || !pending.current) return;
      pending.current = false;
      const spacing = chart.timeScale().options().barSpacing;
      roomAtLiveEdge(chart, n, (AHEAD_ROOM_BARS + insetBars(chart)) * spacing);
    });
  }, [chart, series, on, barsRevision]);

  useEffect(() => {
    if (!on || !chart || !series) {
      setRoomOk(true);
      return undefined;
    }
    const ts = chart.timeScale();
    const check = (range: LogicalRange | null) => setRoomOk(hasRoom(range, lastIndex(chart, series), insetBars(chart)));
    check(ts.getVisibleLogicalRange());
    ts.subscribeVisibleLogicalRangeChange(check);
    return () => {
      try {
        ts.unsubscribeVisibleLogicalRangeChange(check);
      } catch {
        /* the chart is gone with its pane */
      }
    };
  }, [chart, series, on, barsRevision]);

  return roomOk;
}
