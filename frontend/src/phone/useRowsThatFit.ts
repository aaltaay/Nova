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

/**
 * `mounted` names what the box is part of when the list can leave the page and come back (Account's
 * Overview and Calendar): the ref object stays the same across that, so a change of `mounted` is what
 * measures the new element and moves the observer onto it.
 */
export function useRowsThatFit(ref: RefObject<HTMLElement | null>, rowHeight: number, mounted: unknown = null): number {
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
  }, [ref, rowHeight, mounted]);
  return count;
}
