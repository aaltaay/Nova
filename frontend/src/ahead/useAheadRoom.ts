/**
 * Room for Ahead's zone right of the newest candle (ADR 065). When Ahead comes on, and again whenever a new answer
 * arrives, a view that still follows the live edge and is still Nova's (`operatorOwnsView`) is framed like the
 * approved mockup: the last `AHEAD_FRAME_CANDLES` candles, the 15-step zone and a small margin, plus the stock read's
 * word column at the edge right of the zone -- so the zone takes about a quarter of the pane instead of a sliver of a
 * whole session. When the pane's width changes (the Ahead panel docking beside the charts, or leaving) such a view is
 * framed again on the new width. A view the operator zoomed or panned stays exactly where they put it. Then it tells, as the view
 * moves, whether the zone has any room on screen at all -- the scene says so in words when it has none.
 */
import { useEffect, useRef, useState } from 'react';
import { MismatchDirection, type IChartApi, type ISeriesApi, type LogicalRange } from 'lightweight-charts';
import { afterPaintSettles, isFollowingRightEdge, operatorOwnsView } from '../chart';
import { AHEAD_FRAME_CANDLES, AHEAD_FRAME_MARGIN, AHEAD_HORIZON } from './aheadConstants';
import { edgeInset } from './AheadPrimitive';

/** A width change under this many pixels is not a new width (no re-frame). */
const WIDTH_SLACK_PX = 1;
/** Fewer whole steps than this past the newest candle on screen: the zone has no room. */
const ROOM_MIN_STEPS = 2;
/** The word column never takes more than this share of the framed pane. */
const COLUMN_MAX_SHARE = 0.45;
/** A view this close to the frame already is left alone (no needless move). */
const FRAME_SLACK_BARS = 0.5;

/** The newest candle's logical index on the pane, by search (no copy of the bars). */
function lastIndex(chart: IChartApi, series: ISeriesApi<'Candlestick'>): number | null {
  const row = series.dataByIndex(Number.MAX_SAFE_INTEGER, MismatchDirection.NearestLeft);
  return row ? chart.timeScale().timeToIndex(row.time, true) : null;
}

/** Pure: does a visible range leave the zone room past the newest candle? */
export function hasRoom(range: LogicalRange | null, last: number | null): boolean {
  if (!range || last === null) return true;
  return range.to - last >= ROOM_MIN_STEPS;
}

/**
 * Pure: the mockup's frame for a pane `paneW` px wide whose newest candle is `last`, with the stock read's word column
 * `insetPx` wide at the right edge: `AHEAD_FRAME_CANDLES` candles, the zone and its margin, then the column.
 */
export function aheadFrameRange(last: number, paneW: number, insetPx: number): LogicalRange {
  const core = AHEAD_FRAME_CANDLES + AHEAD_HORIZON + AHEAD_FRAME_MARGIN;
  const share = paneW > 0 ? Math.min(COLUMN_MAX_SHARE, Math.max(0, insetPx) / paneW) : 0;
  const span = core / (1 - share);
  const to = last + AHEAD_HORIZON + AHEAD_FRAME_MARGIN + (span - core);
  return { from: to - span, to } as LogicalRange;
}

/** Frame the pane for Ahead when the view is Nova's and follows the live edge; true when it moved the view. */
export function frameForAhead(chart: IChartApi, barCount: number): boolean {
  if (barCount === 0 || operatorOwnsView(chart)) return false;
  try {
    const ts = chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    if (!range || !isFollowingRightEdge(range, barCount)) return false;
    const width = chart.paneSize().width;
    const target = aheadFrameRange(barCount - 1, width, edgeInset(chart, width));
    if (Math.abs(range.from - target.from) < FRAME_SLACK_BARS && Math.abs(range.to - target.to) < FRAME_SLACK_BARS) {
      return false;
    }
    ts.setVisibleLogicalRange(target);
    return true;
  } catch {
    // maintainer: allow-swallow the chart was removed with its pane; nothing to frame
    return false;
  }
}

/**
 * Frame the pane when Ahead comes on and on each new answer (`frameKey`, the answer's minute), after the pane's own
 * paint has applied its view; report whether the zone has room on screen.
 */
export function useAheadRoom(chart: IChartApi | null, series: ISeriesApi<'Candlestick'> | null, on: boolean,
  barsRevision: number, frameKey: string | number | null = null): boolean {
  const framed = useRef<string | null>(null);
  const [roomOk, setRoomOk] = useState(true);

  useEffect(() => {
    if (!on) {
      framed.current = null;
      return undefined;
    }
    const key = String(frameKey ?? 'on');
    if (!chart || !series || framed.current === key) return undefined;
    return afterPaintSettles(() => {
      const n = series.data().length;
      if (n === 0 || framed.current === key) return;
      framed.current = key;
      frameForAhead(chart, n);
    });
  }, [chart, series, on, barsRevision, frameKey]);

  // A new width (the panel docking or leaving): frame again, on the same terms.
  useEffect(() => {
    if (!on || !chart || !series) return undefined;
    const ts = chart.timeScale();
    let width = chart.paneSize().width;
    let cancel = () => {};
    const onSize = (w: number) => {
      if (Math.abs(w - width) < WIDTH_SLACK_PX) return;
      width = w;
      // After the paint at the new width, so the stock read's word column is measured at that width too.
      cancel();
      cancel = afterPaintSettles(() => {
        const n = series.data().length;
        if (n > 0) frameForAhead(chart, n);
      });
    };
    ts.subscribeSizeChange(onSize);
    return () => {
      cancel();
      try {
        ts.unsubscribeSizeChange(onSize);
      } catch {
        /* the chart is gone with its pane */
      }
    };
  }, [chart, series, on]);

  useEffect(() => {
    if (!on || !chart || !series) {
      setRoomOk(true);
      return undefined;
    }
    const ts = chart.timeScale();
    const check = (range: LogicalRange | null) => setRoomOk(hasRoom(range, lastIndex(chart, series)));
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
