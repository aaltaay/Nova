/**
 * Does the tab row need its overflow chevron? Measured, never guessed: the
 * tabs container clips (`overflow: hidden`), so overflow is exactly
 * scrollWidth > clientWidth. Re-measured on resize and whenever the tab list
 * changes. jsdom reports 0 / 0, so tests see "fits".
 */
import { useLayoutEffect, useState, type RefObject } from 'react';

export function useStripOverflow(ref: RefObject<HTMLElement | null>, deps: readonly unknown[]): boolean {
  const [overflowing, setOverflowing] = useState(false);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setOverflowing(el.scrollWidth > el.clientWidth + 1);
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    if (el.parentElement) observer.observe(el.parentElement);
    return () => observer.disconnect();
    // The tab list is the only input that changes the intrinsic width.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref, ...deps]);
  return overflowing;
}
