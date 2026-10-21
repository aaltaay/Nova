/**
 * One frame of the heat map, as numbers (ADR 061): the price range, the book averaged into a grid of time columns x
 * tick rows, the middle of the bid and ask per column, the dots and the volume bars. Pure: the store in, arrays out;
 * `heatPaint.ts` turns them into pixels.
 *
 * Each column is the time-weighted average of every book in force during its slice of the window, so an order that
 * flickers fades instead of speckling. A slice counts as seen only when IBKR's rows covered that price for at least
 * half of it; the rest is "not seen" (black), never an empty book.
 */
import { HEAT_MIN_SPAN_TICKS, HEAT_PAD_TICKS } from './heatMapConstants';
import { heatAliveUntil, heatBursts, heatVolumeAt, type HeatSide, type HeatSnap, type HeatSymbol } from './heatStore';

export interface HeatWindow {
  t0: number;
  t1: number;
}

/** Tick rows `lo`..`hi`, top = hi. */
export interface HeatRange {
  lo: number;
  hi: number;
}

export interface HeatGrid {
  cols: number;
  rows: number;
  /** Row 0 is tick `range.lo` (the bottom). `size[r * cols + c]`: average shares; `seen[...]`: 1 when covered. */
  size: Float32Array;
  seen: Uint8Array;
}

export interface HeatDot {
  t: number;
  price: number;
  shares: number;
  side: HeatSide;
}

/** Index of the last snapshot at or before `t`, or -1. */
export function snapAt(snaps: readonly HeatSnap[], t: number): number {
  let lo = 0;
  let hi = snaps.length - 1;
  let best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (snaps[mid].t <= t) {
      best = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best;
}

/** When snapshot `k` stops being in force: the next book, else while the line was alive (never past `cap`). */
function snapEnd(s: HeatSymbol, k: number, cap: number): number {
  const next = s.snaps[k + 1];
  return Math.min(next ? next.t : heatAliveUntil(s), cap);
}

/** The window's best bid / best ask extremes, padded; null with no book in the window. */
export function heatRange(s: HeatSymbol, w: HeatWindow): HeatRange | null {
  let lo = Number.POSITIVE_INFINITY;
  let hi = Number.NEGATIVE_INFINITY;
  const start = Math.max(0, snapAt(s.snaps, w.t0));
  for (let k = start; k < s.snaps.length && s.snaps[k].t <= w.t1; k += 1) {
    const sn = s.snaps[k];
    if (snapEnd(s, k, w.t1) <= w.t0) continue;
    for (const v of [sn.bb, sn.ba]) {
      if (Number.isFinite(v)) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
    }
  }
  if (!Number.isFinite(lo)) return null;
  lo -= HEAT_PAD_TICKS;
  hi += HEAT_PAD_TICKS;
  const short = HEAT_MIN_SPAN_TICKS - (hi - lo);
  if (short > 0) {
    lo -= Math.floor(short / 2);
    hi += Math.ceil(short / 2);
  }
  return { lo, hi };
}

/** The book averaged into `cols` time columns x the range's tick rows. */
export function heatGrid(s: HeatSymbol, w: HeatWindow, range: HeatRange, cols: number): HeatGrid {
  const rows = range.hi - range.lo + 1;
  const acc = new Float64Array(rows * cols);
  const cov = new Float64Array(rows * cols);
  const covered = new Float64Array(cols);
  const span = w.t1 - w.t0;
  const colW = span / cols;
  const start = Math.max(0, snapAt(s.snaps, w.t0));
  for (let k = start; k < s.snaps.length; k += 1) {
    const sn = s.snaps[k];
    if (sn.t >= w.t1) break;
    const a = Math.max(sn.t, w.t0);
    const b = snapEnd(s, k, w.t1);
    if (b <= a) continue;
    const c0 = Math.max(0, Math.floor((a - w.t0) / colW));
    const c1 = Math.min(cols - 1, Math.floor((b - w.t0) / colW - 1e-9));
    const r0 = Math.max(0, sn.lo - range.lo);
    const r1 = Math.min(rows - 1, sn.lo + sn.sizes.length - 1 - range.lo);
    for (let c = c0; c <= c1; c += 1) {
      const cs = w.t0 + c * colW;
      const wgt = Math.min(b, cs + colW) - Math.max(a, cs);
      if (wgt <= 0) continue;
      covered[c] += wgt;
      for (let r = r0; r <= r1; r += 1) {
        const v = sn.sizes[r + range.lo - sn.lo];
        const i = r * cols + c;
        acc[i] += wgt * v;
        cov[i] += wgt;
      }
    }
  }
  const size = new Float32Array(rows * cols);
  const seen = new Uint8Array(rows * cols);
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const i = r * cols + c;
      if (cov[i] >= colW * 0.5) {
        seen[i] = 1;
        size[i] = acc[i] / cov[i];
      }
    }
  }
  return { cols, rows, size, seen };
}

/** The middle of the best bid and ask (in ticks) in force at the end of each column; NaN where none. */
export function heatMid(s: HeatSymbol, w: HeatWindow, cols: number): Float32Array {
  const out = new Float32Array(cols).fill(Number.NaN);
  const colW = (w.t1 - w.t0) / cols;
  for (let c = 0; c < cols; c += 1) {
    const t = w.t0 + (c + 1) * colW;
    const k = snapAt(s.snaps, t);
    if (k < 0) continue;
    if (snapEnd(s, k, Number.POSITIVE_INFINITY) < t) continue;
    const sn = s.snaps[k];
    if (Number.isFinite(sn.bb) && Number.isFinite(sn.ba)) out[c] = (sn.bb + sn.ba) / 2;
  }
  return out;
}

/** Bursts inside the window of at least `minShares`, biggest first (smaller ones are drawn on top). */
export function heatDots(s: HeatSymbol, w: HeatWindow, minShares: number): HeatDot[] {
  const out: HeatDot[] = [];
  for (const b of heatBursts(s)) {
    const t = (b.t0 + b.t1) / 2;
    if (t < w.t0 || t > w.t1 || b.sz < minShares) continue;
    out.push({ t, price: b.pv / b.sz, shares: b.sz, side: b.side });
  }
  out.sort((x, y) => y.shares - x.shares);
  return out;
}

/** Shares per bar (ask, bid, between) across the window, `bars` bars of whole seconds. */
export function heatVolume(s: HeatSymbol, w: HeatWindow, bars: number): Array<[number, number, number]> {
  const out: Array<[number, number, number]> = Array.from({ length: bars }, () => [0, 0, 0]);
  const per = (w.t1 - w.t0) / bars;
  for (let sec = Math.floor(w.t0); sec < w.t1; sec += 1) {
    const i = Math.floor((sec - w.t0) / per);
    if (i < 0 || i >= bars) continue;
    const v = heatVolumeAt(s, sec);
    out[i][0] += v[0];
    out[i][1] += v[1];
    out[i][2] += v[2];
  }
  return out;
}

/** The book in force at `t` (the right edge), or null when the line was not live then. */
export function heatBookAt(s: HeatSymbol, t: number): HeatSnap | null {
  const k = snapAt(s.snaps, t);
  if (k < 0 || snapEnd(s, k, Number.POSITIVE_INFINITY) < t) return null;
  return s.snaps[k];
}

/** The right edge of the screen: market now, held at the newest data while the feed is quiet (a paused replay). */
export function heatNow(s: HeatSymbol, wallMs: number): number {
  const clock = wallMs / 1000 + s.offset;
  const newest = Math.max(s.lastBookT, s.lastPrintT, s.aliveT);
  if (!Number.isFinite(newest)) return clock;
  return Math.min(clock, newest + 5);
}
