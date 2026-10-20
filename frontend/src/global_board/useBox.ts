/**
 * The size of the box a Global page panel gets (ADR 060 amendment: the page fills the window and never scrolls), so
 * the map and the two charts draw at the size there is. Without ResizeObserver (tests) the fallback stands.
 */
import { useLayoutEffect, useRef, useState, type RefObject } from 'react';

export interface Box {
  width: number;
  height: number;
}

export function useBox<T extends HTMLElement>(fallback: Box): [RefObject<T | null>, Box] {
  const ref = useRef<T | null>(null);
  const [box, setBox] = useState<Box>(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const read = () => {
      const width = Math.floor(el.clientWidth);
      const height = Math.floor(el.clientHeight);
      if (width > 0 && height > 0) {
        setBox((b) => (b.width === width && b.height === height ? b : { width, height }));
      }
    };
    read();
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, box];
}
