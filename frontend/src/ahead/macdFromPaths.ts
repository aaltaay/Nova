/**
 * The MACD fan (ADR 065): Nova's own MACD (12, 26, 9 on closes, `computeMacdPane`) run over the real closes and then
 * on along each of the forecaster's paths, read as quantiles per minute. The MACD itself is never forecast.
 *
 * The real history is read once: the three EMAs' states at the newest completed candle. Each path then extends them
 * in O(15) with the exact recurrences of the chart's MACD (`lightweight-charts-indicators` over `oakscriptjs`
 * `ta.ema`): an EMA starts as the mean of its first `length` values and then moves `(x - ema) * 2/(length+1)`; the
 * MACD line is fast minus slow, the signal an EMA of the MACD line. Tests hold the history to `computeMacdPane`
 * exactly and every extension to a full recompute.
 */
import { CHART_MACD_FAST, CHART_MACD_SIGNAL, CHART_MACD_SLOW } from '../constants';
import type { SceneBand } from './aheadSceneTypes';

interface EmaState {
  len: number;
  mult: number;
  count: number;
  sum: number;
  value: number;
  ready: boolean;
}

export interface MacdState {
  fast: EmaState;
  slow: EmaState;
  signal: EmaState;
}

function emaStart(len: number): EmaState {
  return { len, mult: 2 / (len + 1), count: 0, sum: 0, value: NaN, ready: false };
}

/** One value in; the EMA out (NaN until `len` valid values have arrived). A NaN input holds the EMA. */
function emaPush(s: EmaState, v: number): number {
  const valid = !Number.isNaN(v);
  if (!s.ready) {
    if (!valid) return NaN;
    s.sum += v;
    s.count += 1;
    if (s.count < s.len) return NaN;
    s.value = s.sum / s.count;
    s.ready = true;
    return s.value;
  }
  if (valid) s.value = (v - s.value) * s.mult + s.value;
  return s.value;
}

export function macdStart(): MacdState {
  return { fast: emaStart(CHART_MACD_FAST), slow: emaStart(CHART_MACD_SLOW), signal: emaStart(CHART_MACD_SIGNAL) };
}

/** One close in; the MACD line out (NaN until the slow EMA has started). */
export function macdPush(s: MacdState, close: number): number {
  const line = emaPush(s.fast, close) - emaPush(s.slow, close);
  emaPush(s.signal, line);
  return line;
}

function cloneState(s: MacdState): MacdState {
  return { fast: { ...s.fast }, slow: { ...s.slow }, signal: { ...s.signal } };
}

/** The MACD line over the real closes and the EMAs' states after the newest one. */
export function macdHistory(closes: readonly number[]): { macd: number[]; signal: number[]; state: MacdState } {
  const state = macdStart();
  const macd: number[] = [];
  const signal: number[] = [];
  for (const c of closes) {
    macd.push(macdPush(state, c));
    signal.push(state.signal.ready ? state.signal.value : NaN);
  }
  return { macd, signal, state };
}

/** The MACD line along one path, from the history's state (the state itself is left untouched). */
export function extendMacd(state: MacdState, path: readonly number[]): number[] {
  const s = cloneState(state);
  return path.map((c) => macdPush(s, c));
}

/** Linear-interpolated quantile of an ascending-sorted list. */
export function quantile(sorted: readonly number[], q: number): number {
  if (sorted.length === 0) return NaN;
  const h = (sorted.length - 1) * q;
  const lo = Math.floor(h);
  const hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (h - lo) * (sorted[hi] - sorted[lo]);
}

/** The 10 / 25 / 50 / 75 / 90% band of a set of values at step `k`; null with no finite value. */
export function bandOf(values: readonly number[], k: number): SceneBand | null {
  const s = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (s.length === 0) return null;
  return {
    k, q10: quantile(s, 0.1), q25: quantile(s, 0.25), q50: quantile(s, 0.5), q75: quantile(s, 0.75), q90: quantile(s, 0.9),
  };
}

/**
 * The MACD line's fan per step (`k` = 1 for the first minute after the newest candle) over every path; null when the
 * history is too short for a MACD line at any step.
 */
export function macdFan(history: readonly number[], paths: readonly (readonly number[])[]): SceneBand[] | null {
  if (paths.length === 0) return null;
  const { state } = macdHistory(history);
  const lines = paths.map((p) => extendMacd(state, p));
  const steps = Math.max(...paths.map((p) => p.length));
  const out: SceneBand[] = [];
  for (let k = 0; k < steps; k += 1) {
    const band = bandOf(lines.map((l) => (k < l.length ? l[k] : NaN)), k + 1);
    if (band) out.push(band);
  }
  return out.length ? out : null;
}
