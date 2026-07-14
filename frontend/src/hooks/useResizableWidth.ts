/**
 * Generic drag-to-resize width hook for split layouts (charts | side panel,
 * sidebar | content, etc). Persists the chosen width per `storageKey` so any
 * new resizable panel in the app can opt in with one hook call + one
 * `<ResizeHandle />` — see `components/ResizeHandle.tsx`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface UseResizableWidthOptions {
  /** localStorage key the chosen width is persisted under. */
  storageKey: string;
  /** Width (px) used the first time this key has no saved value. */
  defaultPx: number;
  minPx: number;
  maxPx: number;
  /**
   * Which edge of the panel the handle sits on relative to drag direction.
   * 'end' (default): panel is to the right of the handle, dragging right shrinks it.
   * 'start': panel is to the left of the handle, dragging right grows it.
   */
  anchor?: 'start' | 'end';
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function readStoredWidth(storageKey: string, fallback: number, min: number, max: number): number {
  try {
    const raw = localStorage.getItem(storageKey);
    const parsed = raw != null ? Number(raw) : NaN;
    if (Number.isFinite(parsed)) return clamp(parsed, min, max);
  } catch {
    /* ignore quota / private mode */
  }
  return fallback;
}

export function useResizableWidth({
  storageKey,
  defaultPx,
  minPx,
  maxPx,
  anchor = 'end',
}: UseResizableWidthOptions): {
  width: number;
  onDragStart: (e: React.PointerEvent) => void;
  reset: () => void;
} {
  const [width, setWidth] = useState(() => readStoredWidth(storageKey, defaultPx, minPx, maxPx));
  const widthRef = useRef(width);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  useEffect(() => {
    function handleMove(e: PointerEvent) {
      const drag = dragRef.current;
      if (!drag) return;
      const deltaX = e.clientX - drag.startX;
      const signed = anchor === 'end' ? -deltaX : deltaX;
      setWidth(clamp(drag.startWidth + signed, minPx, maxPx));
    }
    function handleUp() {
      if (!dragRef.current) return;
      dragRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try {
        localStorage.setItem(storageKey, String(widthRef.current));
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
  }, [anchor, maxPx, minPx, storageKey]);

  const onDragStart = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startWidth: widthRef.current };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  const reset = useCallback(() => {
    setWidth(defaultPx);
    try {
      localStorage.removeItem(storageKey);
    } catch {
      /* ignore quota / private mode */
    }
  }, [defaultPx, storageKey]);

  return { width, onDragStart, reset };
}
