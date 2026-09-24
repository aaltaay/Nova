/**
 * Time-scale policy for chart paints.
 *
 * First paint (or Reset Chart) uses the same default window as before:
 * pinned last-N for long 1Min/5Min series, fitContent for 10Sec.
 * Later setData (bars_patch hist fill, rolling cap, older-bar rewrite)
 * must not fitContent / re-pin -- that is the mid-trade zoom-out.
 *
 * Live follow is implicit: if the right edge was on screen, keep the
 * same bar span and advance `to`. If the operator panned away, restore
 * the time window so a prepend/trim does not yank them.
 *
 * A viewport carried onto a different series (a Paper / Live / Sim switch)
 * may name a time window the new bars do not hold -- another day's replay.
 * Restoring it would show an empty pane, so the zoom is kept at the tip.
 */
import type { IChartApi, IRange, Logical, LogicalRange, Time } from 'lightweight-charts';
import { timeScaleRangeForSeries } from '../tickerChartData';

function toLogicalRange(from: number, to: number): LogicalRange {
  return { from: from as Logical, to: to as Logical };
}

/** Bars from the last index that still count as "following" the tip. */
export const CHART_VIEWPORT_FOLLOW_SLACK_BARS = 2;

export interface ChartViewportSnapshot {
  logical: LogicalRange | null;
  time: IRange<Time> | null;
  barCount: number;
}

export type TimeScaleCommand =
  | { kind: 'fitContent' }
  | { kind: 'setVisibleLogicalRange'; range: LogicalRange }
  | { kind: 'setVisibleRange'; range: IRange<Time> };

export function defaultTimeScaleCommand(
  timeframe: string,
  candleCount: number,
): TimeScaleCommand {
  const range = timeScaleRangeForSeries(timeframe, candleCount);
  if (range) return { kind: 'setVisibleLogicalRange', range: toLogicalRange(range.from, range.to) };
  return { kind: 'fitContent' };
}

export function isFollowingRightEdge(
  logical: LogicalRange | null,
  barCount: number,
  slack: number = CHART_VIEWPORT_FOLLOW_SLACK_BARS,
): boolean {
  if (!logical || barCount <= 0) return false;
  return logical.to >= barCount - 1 - slack;
}

/**
 * Advance by the bars that arrived, never clamp to the tip.
 *
 * An operator who pans so the last bar sits mid-pane is still "following" --
 * `logical.to` simply runs past the last index into the right margin. Clamping
 * `to` to `newBarCount - 1` silently ate that margin on every full repaint
 * (backfill, rolling trim, two bars at once), which read as the chart yanking
 * itself flush to the right edge. Shifting by the delta keeps the margin, and
 * is equally correct for an append, a prepend and a rolling trim.
 */
export function followLogicalRange(
  previous: LogicalRange,
  newBarCount: number,
  previousBarCount: number,
): LogicalRange {
  const span = previous.to - previous.from;
  const to = Math.max(0, previous.to + (newBarCount - previousBarCount));
  return toLogicalRange(to - span, to);
}

/** Seconds for an intraday timestamp or a daily `YYYY-MM-DD` / business day. */
function timeSeconds(time: Time): number | null {
  if (typeof time === 'number') return time;
  const ms = typeof time === 'string'
    ? Date.parse(time)
    : Date.UTC(time.year, time.month - 1, time.day);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** False only when both ranges are readable and share no instant. */
export function timeRangesOverlap(a: IRange<Time>, b: IRange<Time>): boolean {
  const [aFrom, aTo, bFrom, bTo] = [a.from, a.to, b.from, b.to].map(timeSeconds);
  if (aFrom == null || aTo == null || bFrom == null || bTo == null) return true;
  return aFrom <= bTo && bFrom <= aTo;
}

/** The operator's bar span, right edge on the newest bar. */
export function tipLogicalRange(span: number, candleCount: number): LogicalRange {
  const to = Math.max(0, candleCount - 1);
  return toLogicalRange(to - span, to);
}

export function paintTimeScaleCommand(
  timeframe: string,
  candleCount: number,
  previous: ChartViewportSnapshot | null,
  /** First..last time of the bars being painted; checks a restored window still lands on them. */
  seriesTime: IRange<Time> | null = null,
): TimeScaleCommand | null {
  if (!previous) return defaultTimeScaleCommand(timeframe, candleCount);
  if (previous.logical && isFollowingRightEdge(previous.logical, previous.barCount)) {
    return {
      kind: 'setVisibleLogicalRange',
      range: followLogicalRange(previous.logical, candleCount, previous.barCount),
    };
  }
  if (previous.time && (!seriesTime || timeRangesOverlap(previous.time, seriesTime))) {
    return { kind: 'setVisibleRange', range: previous.time };
  }
  if (!previous.logical) return null;
  if (!previous.time) return { kind: 'setVisibleLogicalRange', range: previous.logical };
  // The window is not in these bars (another venue's day): keep the zoom, at the tip.
  return {
    kind: 'setVisibleLogicalRange',
    range: tipLogicalRange(previous.logical.to - previous.logical.from, candleCount),
  };
}

export function snapshotChartViewport(
  chart: IChartApi | null,
  barCount: number,
): ChartViewportSnapshot | null {
  if (!chart || barCount <= 0) return null;
  try {
    const ts = chart.timeScale();
    return {
      logical: ts.getVisibleLogicalRange() ?? null,
      time: ts.getVisibleRange() ?? null,
      barCount,
    };
  } catch {
    return null;
  }
}

export function applyTimeScaleCommand(
  chart: IChartApi | null,
  command: TimeScaleCommand | null,
): void {
  if (!chart || !command) return;
  try {
    const ts = chart.timeScale();
    if (command.kind === 'fitContent') ts.fitContent();
    else if (command.kind === 'setVisibleLogicalRange') {
      ts.setVisibleLogicalRange(command.range);
    } else {
      ts.setVisibleRange(command.range);
    }
  } catch {
    /* disposed between setData and rAF -- next paint retries */
  }
}
