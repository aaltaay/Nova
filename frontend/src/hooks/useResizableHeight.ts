/**
 * Drag-to-resize height split for stacked panels
 * (e.g. Stock View depth module above Order Entry).
 * Persists a percentage of the parent stack for the top pane.
 */
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

interface UseResizableHeightOptions {
  /** localStorage key for the top-pane percentage (0–100). */
  storageKey: string;
  /** Top-pane share (%) when nothing is saved. */
  defaultPct: number;
  minPct: number;
  maxPct: number;
  /** Parent stack whose clientHeight defines the drag scale. */
  containerRef: RefObject<HTMLElement | null>;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function readStoredPct(
  storageKey: string,
  fallback: number,
  min: number,
  max: number,
): number {
  try {
    const raw = localStorage.getItem(storageKey);
    const parsed = raw != null ? Number(raw) : NaN;
    if (Number.isFinite(parsed)) return clamp(parsed, min, max);
  } catch {
    /* ignore quota / private mode */
  }
  return fallback;
}

export function useResizableHeight({
  storageKey,
  defaultPct,
  minPct,
  maxPct,
  containerRef,
}: UseResizableHeightOptions): {
  topPct: number;
  onDragStart: (e: React.PointerEvent) => void;
  reset: () => void;
} {
  const [topPct, setTopPct] = useState(() =>
    readStoredPct(storageKey, defaultPct, minPct, maxPct),
  );
  const pctRef = useRef(topPct);
  const dragRef = useRef<{ startY: number; startPct: number } | null>(null);

  useEffect(() => {
    pctRef.current = topPct;
  }, [topPct]);

  useEffect(() => {
    function handleMove(e: PointerEvent) {
      const drag = dragRef.current;
      if (!drag) return;
      const containerH = containerRef.current?.clientHeight ?? 0;
      if (containerH <= 0) return;
      const deltaY = e.clientY - drag.startY;
      const deltaPct = (deltaY / containerH) * 100;
      setTopPct(clamp(drag.startPct + deltaPct, minPct, maxPct));
    }
    function handleUp() {
      if (!dragRef.current) return;
      dragRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try {
        localStorage.setItem(storageKey, String(pctRef.current));
      } catch {
        /* ignore quota / private mode */
      }
    }
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    return () => {
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
    };
  }, [containerRef, maxPct, minPct, storageKey]);

  const onDragStart = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    dragRef.current = { startY: e.clientY, startPct: pctRef.current };
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, []);

  const reset = useCallback(() => {
    setTopPct(defaultPct);
    try {
      localStorage.removeItem(storageKey);
    } catch {
      /* ignore quota / private mode */
    }
  }, [defaultPct, storageKey]);

  return { topPct, onDragStart, reset };
}
