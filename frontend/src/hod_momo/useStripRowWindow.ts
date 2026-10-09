/**
 * The HOD strip rows a scrolling box of any height mounts: the ones in view
 * plus an overscan, with spacers standing in for the rest, so the day's alert
 * count never sets the page's DOM size. The Trader's Focus rail half drew every
 * row of the day (2026-10-09: about 3,300 alerts held its hidden desk window at
 * 21,000 elements, and the window drew 3 frames a second once shown). The box
 * flexes with the rail, so its height is measured; until it is, a fallback
 * stands in. The Scanner's strip knows its own height and windows the same
 * rows with the same math (HodMomoDock).
 */
import { useCallback, useEffect, useRef, useState, type UIEvent } from 'react';
import { computeVisibleRowRange, type VisibleRowRange } from './HodMomoAlertTable';
import {
  HOD_MOMO_STRIP_OVERSCAN_ROWS,
  HOD_MOMO_STRIP_ROW_PX,
  HOD_MOMO_STRIP_WINDOW_FALLBACK_ROWS,
} from './hodMomoStripConstants';

export interface StripRowWindow {
  /** Callback ref for the scrolling box. */
  boxRef: (el: HTMLDivElement | null) => void;
  onScroll: (event: UIEvent<HTMLDivElement>) => void;
  /** Which rows to mount, and the spacer heights around them. */
  range: VisibleRowRange;
  /** Scroll the box just enough that row `index` is in view (the keyboard cursor). */
  reveal: (index: number) => void;
}

const ROW = HOD_MOMO_STRIP_ROW_PX;
const FALLBACK_PX = HOD_MOMO_STRIP_WINDOW_FALLBACK_ROWS * ROW;

export function useStripRowWindow(total: number): StripRowWindow {
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const boxEl = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportPx, setViewportPx] = useState(FALLBACK_PX);

  const boxRef = useCallback((el: HTMLDivElement | null) => {
    boxEl.current = el;
    setBox(el);
    setScrollTop(el?.scrollTop ?? 0);
  }, []);

  useEffect(() => {
    if (!box || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(entries => {
      const h = entries[0]?.contentRect.height ?? 0;
      if (h > 0) setViewportPx(h);
    });
    ro.observe(box);
    return () => ro.disconnect();
  }, [box]);

  const onScroll = useCallback((event: UIEvent<HTMLDivElement>) => setScrollTop(event.currentTarget.scrollTop), []);

  const reveal = useCallback((index: number) => {
    const el = boxEl.current;
    if (!el || index < 0) return;
    const top = index * ROW;
    const height = el.clientHeight || FALLBACK_PX;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (top + ROW > el.scrollTop + height) el.scrollTop = top + ROW - height;
    else return;
    setScrollTop(el.scrollTop);
  }, []);

  // A list that shrank under a scrolled box: window from its new end, never past it.
  const top = Math.min(scrollTop, Math.max(0, total * ROW - viewportPx));
  const range = computeVisibleRowRange(top, total, ROW, viewportPx, HOD_MOMO_STRIP_OVERSCAN_ROWS);
  return { boxRef, onScroll, range, reveal };
}
