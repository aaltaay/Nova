/**
 * "If it breaks" under every wall (ADR 065): Nova's arithmetic on the forecaster's paths, the same raw minute closes
 * the wall-first odds count (closes only; the paths are minute ranges joined by an assumed path shape). Pure.
 *
 * A wall is a zone `[lo, hi]` with a `price`, its edge nearest the price (`lo` for a wall above, `hi` for one below).
 * For the wall ABOVE the price a break is the first close over its FAR edge (`hi`, the zone's top). From that minute
 * on, the break minute included, the first of these decides: a close at or over the next wall above's `price` (that
 * wall's near edge, its `lo`) is follow-through; a close back under this wall's `lo` fails; neither by the horizon is
 * still open. With no next wall the race is only holds (never back under `lo`) against fails. The wall BELOW is the
 * mirror: a break is a close under `lo`, follow-through a close at or under the next wall below's `price` (its `hi`),
 * a fail a close back over `hi`.
 *
 * The words name every wall by its one name (`AHEAD_WORDS.wallName`: its price and its label), as its chip and its
 * card headline do.
 */
import { AHEAD_WORDS, type BreakWords } from './aheadConstants';
import type { AheadWall, AheadWallBreak } from './aheadTypes';

const fmt = (p: number) => (p >= 1 ? p.toFixed(2) : p.toFixed(4));
const nameOf = (w: AheadWall) => AHEAD_WORDS.wallName(fmt(w.price), w.label);

export type BreakOutcome = 'none' | 'follow' | 'fail' | 'open';

/** One path past one wall. `up`: the wall above the price. `next`: the next wall beyond it (null: none). */
export function breakOutcome(path: readonly number[], wall: { lo: number; hi: number }, up: boolean,
  next: number | null): BreakOutcome {
  const broke = (c: number) => (up ? c > wall.hi : c < wall.lo);
  const start = path.findIndex(broke);
  if (start < 0) return 'none';
  for (let k = start; k < path.length; k += 1) {
    const c = path[k];
    if (next !== null && (up ? c >= next : c <= next)) return 'follow';
    if (up ? c < wall.lo : c > wall.hi) return 'fail';
  }
  return 'open';
}

/** The shares for one wall over all `paths`. */
export function wallBreak(paths: readonly (readonly number[])[], wall: AheadWall, up: boolean,
  next: AheadWall | null): AheadWallBreak {
  const counts = { none: 0, follow: 0, fail: 0, open: 0 };
  for (const p of paths) counts[breakOutcome(p, wall, up, next?.price ?? null)] += 1;
  const n = paths.length;
  const nBreak = n - counts.none;
  const of = (x: number) => (nBreak === 0 ? null : x / nBreak);
  return {
    share: n === 0 ? 0 : nBreak / n,
    nBreak,
    next,
    follow: next === null ? null : of(counts.follow),
    fail: of(counts.fail),
    open: of(counts.open),
  };
}

/** One wall's break shares as the card's line and the chart chip's second line take them. */
export function breakWords(b: AheadWallBreak, wall: AheadWall, up: boolean, n: number): BreakWords {
  return {
    up,
    wall: nameOf(wall),
    edge: fmt(wall.price),
    share: b.share,
    n,
    next: b.next ? nameOf(b.next) : null,
    nextPrice: b.next ? fmt(b.next.price) : null,
    follow: b.follow,
    fail: b.fail,
    open: b.open,
  };
}
