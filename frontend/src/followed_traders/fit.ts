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

/**
 * The smallest level at which `ref`'s content fits its height. It starts again from 0 whenever `shape` (what is
 * drawn) or the box's height changes, and checks again whenever a block inside changes size (a picture arriving, a
 * font) -- folding more if needed, never unfolding then, so a fold can never feed back into itself. `overflowing` is
 * true when even the last level does not fit: the box then scrolls rather than hide a trade.
 */
export function useFitLevel(ref: RefObject<HTMLElement | null>, shape: string, max: number) {
  const [state, setState] = useState({ level: 0, shape, height: 0, overflowing: false });
  const [tick, setTick] = useState(0);
  const stale = state.shape !== shape;
  const level = stale ? 0 : state.level;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => {
      const height = el.clientHeight;
      setState((s) => (s.height === height ? s : { ...s, level: 0, height, overflowing: false }));
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
      setState((s) => ({ ...s, level: 0, shape, overflowing: false }));
      return;
    }
    const over = el.scrollHeight > el.clientHeight + 1;
    if (over && state.level < max) setState((s) => ({ ...s, level: s.level + 1 }));
    else if (over !== state.overflowing && (!over || state.level >= max)) setState((s) => ({ ...s, overflowing: over }));
  }, [ref, stale, shape, max, state.level, state.overflowing, tick]);

  return { level, overflowing: !stale && state.overflowing };
}
