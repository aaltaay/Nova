/**
 * SVG geometry for the equity / P&L line. Pure.
 *
 * The history is event-marked (one point after every fill and rollover), so
 * the value HOLDS between events: the line is a step, never a slope drawn
 * between two events, and the last value extends flat to the right edge.
 * The curve is the selected range's (QA W13): P&L counts from the range's
 * start, not from the day the ledger opened, and its last point is the
 * account's live mark at the venue's now -- the same figure as the headline
 * and Day's P&L -- rather than positions priced at their last fill (QA W1).
 */
import type { AccountPerfMode } from '../constantGroups/account_page';
import type { PracticeHistory } from './accountHistoryTypes';

export interface SeriesPoint {
  ts: number;
  value: number;
}

export interface LineGeometry {
  line: string;
  area: string;
  min: number;
  max: number;
  /** Y of the baseline (0 for P&L modes, the range's opening value for value) when inside the range. */
  baselineY: number | null;
  last: { x: number; y: number; value: number } | null;
  ticks: Array<{ y: number; value: number }>;
  /** The tick step, so labels carry the decimals the step needs (W26). */
  step: number;
}

/** What the account payload says now: open P&L and net liquidation at the live mark. */
export interface LiveMarks {
  openPnl: number | null;
  netLiquidation: number | null;
}

const finiteOrNull = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : n;

/**
 * The curve for one display mode over the selected range.
 *
 * P&L: realized since the range began plus open P&L -- each event point's
 * cumulative realized less what was realized before the range, plus its open
 * P&L -- ending at `components.realized + live open P&L` (the headline).
 * P&L %: the same over the value the range started from. Value: net
 * liquidation, ending at the live figure; its baseline is the value before
 * the range's P&L, so the value and P&L curves are the same line.
 */
export function rangeSeries(
  history: PracticeHistory,
  mode: AccountPerfMode,
  live: LiveMarks,
  nowTs: number,
): { series: SeriesPoint[]; baseline: number } {
  const points = history.equity;
  const realizedBefore = points.length
    ? points[points.length - 1].realized - history.components.realized
    : 0;
  const rangeBase = history.starting_cash + realizedBefore;
  const lastTs = points.length ? points[points.length - 1].ts : null;
  const append = (series: SeriesPoint[], value: number | null): SeriesPoint[] =>
    value != null && lastTs != null && nowTs >= lastTs ? [...series, { ts: nowTs, value }] : series;
  if (mode === 'value') {
    const series = points.map((p) => ({ ts: p.ts, value: p.net_liquidation }));
    return { series: append(series, finiteOrNull(live.netLiquidation)), baseline: rangeBase };
  }
  const open = finiteOrNull(live.openPnl);
  const pnl = append(
    points.map((p) => ({ ts: p.ts, value: p.realized - realizedBefore + p.unrealized })),
    open == null ? null : history.components.realized + open,
  );
  if (mode === 'pnl') return { series: pnl, baseline: 0 };
  if (!(rangeBase > 0)) return { series: [], baseline: 0 };
  return { series: pnl.map((p) => ({ ts: p.ts, value: (p.value / rangeBase) * 100 })), baseline: 0 };
}

/** Decimals a tick label needs at `step`: money shows cents under a dollar (W26). */
export function tickDecimals(step: number, kind: 'money' | 'pct'): number {
  if (!(step > 0) || step >= 1) return 0;
  if (kind === 'money') return 2;
  return step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3;
}

export interface Frame {
  width: number;
  height: number;
  padLeft: number;
  padRight: number;
  padTop: number;
  padBottom: number;
}

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
  const empty: LineGeometry = { line: '', area: '', min: 0, max: 0, baselineY: null, last: null, ticks: [], step: 1 };
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
    step,
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
