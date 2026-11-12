/**
 * How many rows of a fixed height fit in a box right now. A phone list never scrolls, so it shows
 * exactly what fits and pages the rest.
 */
import { useLayoutEffect, useState, type RefObject } from 'react';

export function rowsThatFit(boxHeight: number, rowHeight: number): number {
  if (!(boxHeight > 0) || !(rowHeight > 0)) return 1;
  // A hair of rounding must not cost a row: the box is laid out in fractional pixels.
  return Math.max(1, Math.floor((boxHeight + 0.5) / rowHeight));
}

export function useRowsThatFit(ref: RefObject<HTMLElement | null>, rowHeight: number): number {
  const [count, setCount] = useState(1);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setCount(rowsThatFit(el.clientHeight, rowHeight));
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, rowHeight]);
  return count;
}
