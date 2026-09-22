/**
 * Bottom-edge drag for the HOD Momo strip. The live ceiling is 40% of the
 * content column the strip sits in (measured at drag start); the height snaps
 * to whole rows while dragging, so state only changes on a row boundary.
 */
import { useCallback, useRef, useState, type PointerEvent, type RefObject } from 'react';
import {
  HOD_MOMO_STRIP_FALLBACK_CONTENT_PX,
} from './hodMomoStripConstants';
import { snapStripRows, stripMaxRowsFor, stripRowsToPx } from './hodMomoStripPersist';

type Args = {
  rows: number;
  setRows: (rows: number) => void;
  rootRef: RefObject<HTMLElement | null>;
};

/** Height of the column that hosts the strip (its parent), or a fallback. */
export function measureContentHeight(root: HTMLElement | null): number {
  const host = root?.parentElement ?? null;
  const h = host?.getBoundingClientRect().height ?? 0;
  if (h > 0) return h;
  if (typeof window !== 'undefined' && window.innerHeight > 0) return window.innerHeight;
  return HOD_MOMO_STRIP_FALLBACK_CONTENT_PX;
}

export function useHodMomoStripResize({ rows, setRows, rootRef }: Args) {
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ y: number; px: number; maxRows: number } | null>(null);

  const onPointerDown = useCallback(
    (e: PointerEvent<HTMLElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      const target = e.currentTarget;
      const maxRows = stripMaxRowsFor(measureContentHeight(rootRef.current));
      drag.current = { y: e.clientY, px: stripRowsToPx(rows), maxRows };
      setDragging(true);
      try {
        target.setPointerCapture(e.pointerId);
      } catch {
        /* jsdom / no pointer capture */
      }

      const onMove = (ev: globalThis.PointerEvent) => {
        if (!drag.current) return;
        const px = drag.current.px + (ev.clientY - drag.current.y);
        setRows(snapStripRows(px, drag.current.maxRows));
      };
      const onUp = (ev: globalThis.PointerEvent) => {
        try {
          target.releasePointerCapture(ev.pointerId);
        } catch {
          /* ignore */
        }
        drag.current = null;
        setDragging(false);
        target.removeEventListener('pointermove', onMove);
        target.removeEventListener('pointerup', onUp);
        target.removeEventListener('pointercancel', onUp);
      };
      target.addEventListener('pointermove', onMove);
      target.addEventListener('pointerup', onUp);
      target.addEventListener('pointercancel', onUp);
    },
    [rows, setRows, rootRef],
  );

  return { dragging, onPointerDown };
}
