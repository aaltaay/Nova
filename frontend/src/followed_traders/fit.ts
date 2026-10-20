/**
 * The followed traders' page has no page scrollbar (operator, 2026-10-13). When the traders' blocks do not fit the window,
 * closed rows drop to one line first, then each trader's oldest closed trades fold into "+N earlier", one at a time
 * from whoever shows the most. Open rows, on top of each table, never fold. `useFitLevel` finds the smallest level that
 * fits by measuring; `fitPlan` says what a level means. Pure apart from the hook.
 */
import { useLayoutEffect, useState, type RefObject } from 'react';

export interface FitPlan {
  compact: boolean;
  /** Closed trades folded per trader, oldest first. */
  folded: Record<string, number>;
}

/** Level 0 is everything at full size, 1 one-line closed rows, and each level past that folds one more closed trade. */
export function fitPlan(level: number, closed: [name: string, count: number][]): FitPlan {
  const folded: Record<string, number> = {};
  const shown = new Map(closed);
  for (let left = level - 1; left > 0; left -= 1) {
    let pick: string | null = null;
    for (const [name, n] of shown) {
      if (n > 0 && (pick === null || n > (shown.get(pick) ?? 0))) pick = name;
    }
    if (pick === null) break;
    shown.set(pick, (shown.get(pick) ?? 0) - 1);
    folded[pick] = (folded[pick] ?? 0) + 1;
  }
  return { compact: level >= 1, folded };
}

export function maxFitLevel(closed: [string, number][]): number {
  return 1 + closed.reduce((sum, [, n]) => sum + n, 0);
}

interface FitSearch {
  shape: string;
  height: number;
  /** The level drawn now: a probe while `lo < hi`, the answer once they meet. */
  level: number;
  /** Every level below `lo` is known not to fit; `hi` (capped at `max`) is the deepest level the answer can be. */
  lo: number;
  hi: number;
  overflowing: boolean;
}

/** Search `[lo, max]`, probing `lo` first: on most redraws the current level still fits and one measure settles it. */
const searchFrom = (shape: string, height: number, lo: number): FitSearch =>
  ({ shape, height, level: lo, lo, hi: Number.POSITIVE_INFINITY, overflowing: false });

/**
 * The smallest level at which `ref`'s content fits its height. It starts again from 0 whenever `shape` (what is
 * drawn) or the box's height changes, and checks again whenever a block inside changes size (a picture arriving, a
 * font) -- folding more if needed, never unfolding then, so a fold can never feed back into itself. `overflowing` is
 * true when even the last level does not fit: the box then scrolls rather than hide a trade.
 *
 * Folding only ever shortens the content, so the level is found by halving `[lo, hi]`: about log2(max) measured
 * redraws before paint. Walking one level per redraw hit React's limit of 50 nested updates once a day passed ~50
 * closed trades (React #185, 2026-10-20).
 */
export function useFitLevel(ref: RefObject<HTMLElement | null>, shape: string, max: number) {
  const [state, setState] = useState<FitSearch>(() => searchFrom(shape, 0, 0));
  const [tick, setTick] = useState(0);
  const stale = state.shape !== shape;
  const level = stale ? 0 : Math.min(state.level, max);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => {
      const height = el.clientHeight;
      setState((s) => (s.height === height ? s : searchFrom(s.shape, height, 0)));
      setTick((t) => t + 1);
    });
    observer.observe(el);
    for (const child of el.children) observer.observe(child);
    return () => observer.disconnect();
  }, [ref, shape]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (stale) {
      setState((s) => searchFrom(shape, s.height, 0));
      return;
    }
    const over = el.scrollHeight > el.clientHeight + 1;
    const hi = Math.min(state.hi, max);
    if (state.lo >= hi) {
      // Settled at `level`: a block inside grew and it no longer fits -- fold further, never back.
      if (over && level < max) setState(searchFrom(shape, state.height, level + 1));
      else if (over !== state.overflowing) setState({ ...state, overflowing: over });
      return;
    }
    const lo = over ? level + 1 : state.lo;
    const top = over ? hi : level;
    setState({ ...state, lo, hi: top, level: lo >= top ? top : Math.floor((lo + top) / 2), overflowing: false });
  }, [ref, stale, shape, max, state, level, tick]);

  return { level, overflowing: !stale && state.overflowing };
}
