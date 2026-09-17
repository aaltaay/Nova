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

export function followLogicalRange(
  previous: LogicalRange,
  newBarCount: number,
): LogicalRange {
  const span = previous.to - previous.from;
  const to = Math.max(0, newBarCount - 1);
  return toLogicalRange(to - span, to);
}

export function paintTimeScaleCommand(
  timeframe: string,
  candleCount: number,
  previous: ChartViewportSnapshot | null,
): TimeScaleCommand | null {
  if (!previous) return defaultTimeScaleCommand(timeframe, candleCount);
  if (previous.logical && isFollowingRightEdge(previous.logical, previous.barCount)) {
    return {
      kind: 'setVisibleLogicalRange',
      range: followLogicalRange(previous.logical, candleCount),
    };
  }
  if (previous.time) return { kind: 'setVisibleRange', range: previous.time };
  if (previous.logical) return { kind: 'setVisibleLogicalRange', range: previous.logical };
  return null;
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
