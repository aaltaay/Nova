/**
 * Fixed-size row windowing for long lists (virtual scroll).
 * Only the visible slice (+ overscan) is meant to be mounted in the DOM.
 */
import { useCallback, useMemo, useRef, useState } from 'react';

export interface WindowSlice {
  startIndex: number;
  endIndex: number;
  offsetTop: number;
  offsetBottom: number;
}

/** Pure window math — unit-tested without a React renderer. */
export function computeWindowSlice(
  count: number,
  scrollTop: number,
  rowHeightPx: number,
  visibleRows: number,
  overscan: number,
): WindowSlice {
  if (count <= 0 || rowHeightPx <= 0) {
    return { startIndex: 0, endIndex: 0, offsetTop: 0, offsetBottom: 0 };
  }
  const top = Math.max(0, scrollTop);
  const rawStart = Math.floor(top / rowHeightPx);
  const startIndex = Math.max(0, rawStart - overscan);
  const endIndex = Math.min(count, rawStart + visibleRows + overscan);
  return {
    startIndex,
    endIndex,
    offsetTop: startIndex * rowHeightPx,
    offsetBottom: Math.max(0, (count - endIndex) * rowHeightPx),
  };
}

export interface WindowedRows extends WindowSlice {
  viewportHeight: number;
  onScroll: (scrollTop: number) => void;
}

export function useWindowedRows(
  count: number,
  rowHeightPx: number,
  visibleRows: number,
  overscan: number,
): WindowedRows {
  const [scrollTop, setScrollTop] = useState(0);
  const viewportHeight = visibleRows * rowHeightPx;
  const rafRef = useRef<number | null>(null);
  const scrollPendingRef = useRef(0);

  const onScroll = useCallback((nextTop: number) => {
    // rAF-throttle: raw scroll events were flooding React setState and feeling frozen.
    scrollPendingRef.current = Math.max(0, nextTop);
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      setScrollTop(scrollPendingRef.current);
    });
  }, []);

  const slice = useMemo(
    () => computeWindowSlice(count, scrollTop, rowHeightPx, visibleRows, overscan),
    [count, scrollTop, rowHeightPx, visibleRows, overscan],
  );

  return { ...slice, viewportHeight, onScroll };
}
