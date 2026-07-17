/**
 * Persisted width for the quote side panel + drag handlers for the splitter.
 * Dragging the handle left widens the right panel; right narrows it.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  SIDE_PANEL_MAX_VIEWPORT_PCT,
  SIDE_PANEL_MAX_WIDTH_PX,
  SIDE_PANEL_MIN_WIDTH_PX,
  SCANNER_MIN_REMAINING_PX,
  SIDE_PANEL_STACK_BREAKPOINT_PX,
  SIDE_PANEL_WIDTH_PX,
  SIDE_PANEL_WIDTH_STORAGE_KEY,
} from '../constants';

function clampWidth(px: number, viewportW: number): number {
  const viewportCap = Math.floor((viewportW * SIDE_PANEL_MAX_VIEWPORT_PCT) / 100);
  const leaveScanner = Math.max(SIDE_PANEL_MIN_WIDTH_PX, viewportW - SCANNER_MIN_REMAINING_PX);
  const max = Math.min(SIDE_PANEL_MAX_WIDTH_PX, viewportCap, leaveScanner);
  return Math.max(SIDE_PANEL_MIN_WIDTH_PX, Math.min(max, Math.round(px)));
}

function loadWidth(): number {
  try {
    const raw = localStorage.getItem(SIDE_PANEL_WIDTH_STORAGE_KEY);
    if (!raw) return SIDE_PANEL_WIDTH_PX;
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) {
      return clampWidth(n, typeof window !== 'undefined' ? window.innerWidth : 1600);
    }
  } catch {
    // ignore
  }
  return SIDE_PANEL_WIDTH_PX;
}

export function useSidePanelWidth() {
  const [widthPx, setWidthPx] = useState(loadWidth);
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);

  useEffect(() => {
    function onResize() {
      setWidthPx(w => clampWidth(w, window.innerWidth));
    }
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const persist = useCallback((w: number) => {
    try {
      localStorage.setItem(SIDE_PANEL_WIDTH_STORAGE_KEY, String(w));
    } catch {
      // ignore
    }
  }, []);

  const onHandlePointerDown = useCallback((e: React.PointerEvent<HTMLElement>) => {
    if (window.innerWidth <= SIDE_PANEL_STACK_BREAKPOINT_PX) return;
    e.preventDefault();
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    dragRef.current = { startX: e.clientX, startW: widthPx };
    setDragging(true);
    document.body.classList.add('is-resizing-side-panel');
  }, [widthPx]);

  useEffect(() => {
    if (!dragging) return;

    function onMove(e: PointerEvent) {
      const drag = dragRef.current;
      if (!drag) return;
      // Handle sits on the left edge of the right panel: move left → wider panel.
      const next = clampWidth(drag.startW + (drag.startX - e.clientX), window.innerWidth);
      setWidthPx(next);
    }

    function onUp() {
      dragRef.current = null;
      setDragging(false);
      document.body.classList.remove('is-resizing-side-panel');
      setWidthPx(w => {
        persist(w);
        return w;
      });
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      document.body.classList.remove('is-resizing-side-panel');
    };
  }, [dragging, persist]);

  return { widthPx, dragging, onHandlePointerDown };
}
