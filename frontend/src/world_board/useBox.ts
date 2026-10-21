/**
 * The size of the box a world board panel gets (the Global and Forex pages fill the window and never scroll, ADR 060
 * amendment, ADR 061), so the maps and the charts draw at the size there is. Without ResizeObserver (tests) the fallback stands.
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
