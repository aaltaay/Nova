/**
 * SVG geometry for the equity / P&L line. Pure.
 *
 * The series is event-marked (one point after every fill and rollover), so
 * the value HOLDS between events: the line is a step, never a slope drawn
 * between two events, and the last value extends flat to the right edge.
 */
import type { AccountPerfMode } from '../constantGroups/account_page';
import type { EquityPoint } from './accountHistoryTypes';

export interface SeriesPoint {
  ts: number;
  value: number;
}

export interface LineGeometry {
  line: string;
  area: string;
  min: number;
  max: number;
  /** Y of the baseline (0 for P&L modes, starting cash for value) when inside the range. */
  baselineY: number | null;
  last: { x: number; y: number; value: number } | null;
  ticks: Array<{ y: number; value: number }>;
}

export interface Frame {
  width: number;
  height: number;
  padLeft: number;
  padRight: number;
  padTop: number;
  padBottom: number;
}

/** Map equity points to the chart's series for one display mode. */
export function equitySeries(points: EquityPoint[], mode: AccountPerfMode, startingCash: number): SeriesPoint[] {
  return points.map((p) => ({
    ts: p.ts,
    value:
      mode === 'value'
        ? p.net_liquidation
        : mode === 'pct'
          ? startingCash > 0 ? ((p.net_liquidation - startingCash) / startingCash) * 100 : 0
          : p.net_liquidation - startingCash,
  }));
}

export const seriesBaseline = (mode: AccountPerfMode, startingCash: number): number =>
  mode === 'value' ? startingCash : 0;

/** A "nice" tick step covering roughly `target` ticks across `span`. */
export function niceStep(span: number, target = 3): number {
  if (!(span > 0)) return 1;
  const raw = span / target;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return nice * magnitude;
}

export function lineGeometry(
  series: SeriesPoint[],
  frame: Frame,
  baseline: number,
  endTs: number | null = null,
): LineGeometry {
  const empty: LineGeometry = { line: '', area: '', min: 0, max: 0, baselineY: null, last: null, ticks: [] };
  if (!series.length) return empty;
  const values = series.map((p) => p.value);
  let min = Math.min(...values, baseline);
  let max = Math.max(...values, baseline);
  if (max - min < 1e-9) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  min -= span * 0.08;
  max += span * 0.08;
  const t0 = series[0].ts;
  const t1 = Math.max(endTs ?? series[series.length - 1].ts, series[series.length - 1].ts, t0 + 1);
  const x0 = frame.padLeft;
  const x1 = frame.width - frame.padRight;
  const y0 = frame.padTop;
  const y1 = frame.height - frame.padBottom;
  const X = (ts: number): number => x0 + ((x1 - x0) * (ts - t0)) / (t1 - t0);
  const Y = (v: number): number => y1 - ((y1 - y0) * (v - min)) / (max - min);
  const f = (n: number): string => n.toFixed(1);

  let line = '';
  let prevY: number | null = null;
  series.forEach((p, i) => {
    const x = X(p.ts);
    const y = Y(p.value);
    if (i === 0) line += `M${f(x)} ${f(y)}`;
    else line += `H${f(x)}V${f(y)}`;
    prevY = y;
  });
  const lastX = X(t1);
  if (prevY != null && lastX > X(series[series.length - 1].ts)) line += `H${f(lastX)}`;
  const baseY = Y(baseline);
  const area = `${line}V${f(baseY)}H${f(X(t0))}Z`;
  const last = series[series.length - 1];
  const step = niceStep(max - min);
  const ticks: Array<{ y: number; value: number }> = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
    ticks.push({ y: Y(v), value: Math.abs(v) < 1e-9 ? 0 : v });
  }
  return {
    line,
    area,
    min,
    max,
    baselineY: baseline >= min && baseline <= max ? baseY : null,
    last: { x: lastX, y: Y(last.value), value: last.value },
    ticks,
  };
}

/** X of a timestamp in the frame the geometry was built with (fill markers). */
export function xForTs(series: SeriesPoint[], frame: Frame, ts: number, endTs: number | null = null): number | null {
  if (!series.length) return null;
  const t0 = series[0].ts;
  const t1 = Math.max(endTs ?? series[series.length - 1].ts, series[series.length - 1].ts, t0 + 1);
  if (ts < t0 || ts > t1) return null;
  return frame.padLeft + ((frame.width - frame.padRight - frame.padLeft) * (ts - t0)) / (t1 - t0);
}

/** The series value holding at `ts` (the last point at or before it). */
export function valueAt(series: SeriesPoint[], ts: number): number | null {
  let best: SeriesPoint | null = null;
  for (const p of series) {
    if (p.ts <= ts) best = p;
    else break;
  }
  return best?.value ?? null;
}
