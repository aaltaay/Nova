/**
 * Volume by price for one stretch of 1-minute bars (plan §5.1): the histogram, its point of control and its value
 * area. Pure. The profile is built from 1-minute bars, never from the 5-minute candles it is drawn over.
 */
import { VP_MIN_ROW, VP_ROWS, VP_VALUE_AREA_PCT } from './volumeProfileConstants';

/** One bar: `t` is its start in epoch seconds. */
export interface ProfileBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface VolumeProfile {
  /** The stretch measured, epoch seconds, `[from, to)`. */
  from: number;
  to: number;
  low: number;
  high: number;
  rowSize: number;
  /** Volume per row, row 0 lowest: on bars that closed at or above their open, and below it. Colour only. */
  up: number[];
  down: number[];
  total: number;
  pocRow: number;
  vahRow: number;
  valRow: number;
  /** The POC row's middle; VAH the top of the value area, VAL its bottom. */
  poc: number;
  vah: number;
  val: number;
}

/** The value area: grown from the POC two rows at a time toward the heavier side until it holds `pct` of the volume. */
function valueArea(rows: number[], pocRow: number, pct: number): [number, number] {
  const total = rows.reduce((a, b) => a + b, 0);
  const target = (total * pct) / 100;
  let lo = pocRow;
  let hi = pocRow;
  let held = rows[pocRow];
  while (held < target && (lo > 0 || hi < rows.length - 1)) {
    const aboveRows = Math.min(2, rows.length - 1 - hi);
    const belowRows = Math.min(2, lo);
    let above = 0;
    for (let i = 1; i <= aboveRows; i += 1) above += rows[hi + i];
    let below = 0;
    for (let i = 1; i <= belowRows; i += 1) below += rows[lo - i];
    if (aboveRows > 0 && (belowRows === 0 || above >= below)) {
      hi += aboveRows;
      held += above;
    } else {
      lo -= belowRows;
      held += below;
    }
  }
  return [lo, hi];
}

/** The busiest row; a tie goes to the row nearest the middle of the range. */
function pointOfControl(rows: number[]): number {
  const mid = (rows.length - 1) / 2;
  let best = 0;
  for (let i = 1; i < rows.length; i += 1) {
    if (rows[i] > rows[best] || (rows[i] === rows[best] && Math.abs(i - mid) < Math.abs(best - mid))) best = i;
  }
  return best;
}

/** The profile of the bars starting in `[from, to)`; null when none traded there. Each bar's volume is spread evenly
 * over the rows its high-low range covers. */
export function buildProfile(
  bars: readonly ProfileBar[],
  from: number,
  to: number,
  rowCount = VP_ROWS,
  valueAreaPct = VP_VALUE_AREA_PCT,
): VolumeProfile | null {
  const inside = bars.filter((b) => b.t >= from && b.t < to && b.v > 0 && b.h >= b.l);
  if (inside.length === 0) return null;
  const low = Math.min(...inside.map((b) => b.l));
  const high = Math.max(...inside.map((b) => b.h));
  const rowSize = Math.max(VP_MIN_ROW, (high - low) / rowCount);
  const n = Math.max(1, Math.ceil((high - low) / rowSize - 1e-9));
  const up = new Array<number>(n).fill(0);
  const down = new Array<number>(n).fill(0);
  const rowOf = (price: number) => Math.min(n - 1, Math.max(0, Math.floor((price - low) / rowSize)));
  for (const b of inside) {
    const side = b.c >= b.o ? up : down;
    const first = rowOf(b.l);
    const last = rowOf(b.h);
    if (first === last) {
      side[first] += b.v;
      continue;
    }
    const span = b.h - b.l;
    for (let r = first; r <= last; r += 1) {
      const overlap = Math.min(b.h, low + (r + 1) * rowSize) - Math.max(b.l, low + r * rowSize);
      if (overlap > 0) side[r] += (b.v * overlap) / span;
    }
  }
  const rows = up.map((u, i) => u + down[i]);
  const total = rows.reduce((a, b) => a + b, 0);
  const pocRow = pointOfControl(rows);
  const [valRow, vahRow] = valueArea(rows, pocRow, valueAreaPct);
  return {
    from, to, low, high, rowSize, up, down, total, pocRow, vahRow, valRow,
    poc: low + (pocRow + 0.5) * rowSize,
    vah: low + (vahRow + 1) * rowSize,
    val: low + valRow * rowSize,
  };
}
