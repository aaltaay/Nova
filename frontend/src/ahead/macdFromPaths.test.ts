import { describe, expect, it } from 'vitest';
import { computeMacdPane, type IndicatorBar } from '../chartIndicators';
import { bandOf, extendMacd, macdFan, macdHistory, quantile } from './macdFromPaths';

/** A made-up wandering close series (deterministic). */
function closes(n: number, seed = 7): number[] {
  let x = seed;
  let p = 4;
  const out: number[] = [];
  for (let i = 0; i < n; i += 1) {
    x = (x * 1103515245 + 12345) % 2147483648;
    p = Math.max(0.5, p + ((x / 2147483648) - 0.5) * 0.08);
    out.push(Number(p.toFixed(4)));
  }
  return out;
}

const bars = (cs: number[]): IndicatorBar[] => cs.map((c, i) => ({
  time: 1_000_000 + i * 60, open: c, high: c, low: c, close: c, volume: 0,
}));

const valuesOf = (pts: ReturnType<typeof computeMacdPane>['macd']) => pts.map((p) => ('value' in p ? p.value : NaN));

describe('the MACD fan', () => {
  it.each([5, 30, 34, 40, 400])('reads the same MACD line and signal over %i real candles as the chart', (n) => {
    const cs = closes(n);
    const pane = computeMacdPane(bars(cs));
    const mine = macdHistory(cs);
    const want = valuesOf(pane.macd);
    expect(mine.macd.map((v) => (Number.isNaN(v) ? null : v))).toEqual(want.map((v) => (Number.isNaN(v) ? null : v)));
    const signal = valuesOf(pane.signal);
    expect(mine.signal.map((v) => (Number.isNaN(v) ? null : v))).toEqual(signal.map((v) => (Number.isNaN(v) ? null : v)));
  });

  it.each([20, 30, 40, 300])('extends each path in step with a full recompute over %i candles of history', (n) => {
    const history = closes(n, 3);
    const { state } = macdHistory(history);
    for (const seed of [11, 23, 57, 91]) {
      const path = closes(15, seed).map((c) => c + history[history.length - 1] - 4);
      const ext = extendMacd(state, path);
      const full = valuesOf(computeMacdPane(bars([...history, ...path])).macd).slice(history.length);
      ext.forEach((v, k) => {
        if (Number.isNaN(full[k])) expect(Number.isNaN(v)).toBe(true);
        else expect(Math.abs(v - full[k])).toBeLessThan(1e-9);
      });
    }
  });

  it('leaves the history state untouched by an extension', () => {
    const { state } = macdHistory(closes(60));
    const before = JSON.stringify(state);
    extendMacd(state, closes(15, 5));
    expect(JSON.stringify(state)).toBe(before);
  });

  it('reads quantiles in order per minute, and has no fan without a MACD line', () => {
    const history = closes(200);
    const paths = [3, 5, 8, 13, 21, 34, 55, 89].map((s) => closes(15, s).map((c) => c + history[199] - 4));
    const fan = macdFan(history, paths);
    expect(fan).toHaveLength(15);
    for (const b of fan ?? []) {
      expect(b.q10).toBeLessThanOrEqual(b.q25);
      expect(b.q25).toBeLessThanOrEqual(b.q50);
      expect(b.q50).toBeLessThanOrEqual(b.q75);
      expect(b.q75).toBeLessThanOrEqual(b.q90);
    }
    expect(fan?.[0].k).toBe(1);
    expect(macdFan(closes(3), paths)).toBeNull();
    expect(macdFan(history, [])).toBeNull();
  });

  it('interpolates quantiles linearly', () => {
    expect(quantile([0, 10], 0.25)).toBe(2.5);
    expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3);
    expect(bandOf([NaN], 1)).toBeNull();
  });
});
