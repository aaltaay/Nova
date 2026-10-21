/**
 * The Ahead panel's place on the page (ADR 065), measured after layout: the rule is `aheadSheetPlace.ts`. Over the
 * other panes it starts below the chart grid's toolbar, so the toolbar stays in reach. Docked, it marks its holder
 * (the chart grid's positioned parent) `ahead-dock--left` / `--right` with the panel's width, and the holder gives the
 * charts that much less room (`aheadSheet.css`); closing the panel hands it back. The 1-minute pane then re-frames
 * for the zone on its new width (`useAheadRoom.ts`) unless the operator owns its view. It ends at the holder's
 * bottom or the window's, whichever is higher, so its body scrolls to the last card instead of running off-screen.
 */
import { useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { samePlace, sheetPlace, useKeepClear, type SheetPlace } from './aheadSheetPlace';

/** The chart grid's toolbar (its bottom is where the panel starts over the panes). */
const TOOLBAR_SELECTOR = '.chart-desk-toolbar';
export const DOCK_CLASS = { left: 'ahead-dock--left', right: 'ahead-dock--right' } as const;
export const DOCK_WIDTH_VAR = '--ahead-dock-w';

export interface PlacedSheet extends SheetPlace {
  /** Pixels from the holder's top to the panel's top. */
  top: number;
  /** Pixels from the holder's bottom up to the panel's bottom: the part of the holder below the window. */
  bottom: number;
}

/** How far the holder runs past the window's bottom (0 when it ends inside the window). Pure. */
export function belowWindow(holderBottom: number, windowHeight: number): number {
  return Math.max(0, Math.round(holderBottom - windowHeight));
}

export function useSheetPlace(symbol: string, open: boolean): {
  ref: RefObject<HTMLElement | null>;
  place: PlacedSheet | null;
} {
  const ref = useRef<HTMLElement | null>(null);
  const keep = useKeepClear(symbol);
  const [place, setPlace] = useState<PlacedSheet | null>(null);
  const current = useRef<SheetPlace | null>(null);

  useLayoutEffect(() => {
    const holder = ref.current?.offsetParent;
    if (!open || !holder) {
      current.current = null;
      return undefined;
    }
    const measure = () => {
      const r = holder.getBoundingClientRect();
      const next = sheetPlace({ left: r.left, right: r.right }, keep, current.current);
      const bar = next.dock ? null : holder.querySelector(TOOLBAR_SELECTOR);
      const top = bar ? Math.max(0, bar.getBoundingClientRect().bottom - r.top) : 0;
      const bottom = belowWindow(r.bottom, window.innerHeight);
      if (samePlace(current.current, next)) {
        setPlace(was => (was && Math.abs(was.top - top) < 1 && was.bottom === bottom ? was : { ...next, top, bottom }));
        return;
      }
      current.current = next;
      setPlace({ ...next, top, bottom });
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [open, keep]);

  const dockSide = open && place?.dock ? place.side : null;
  const dockWidth = Math.round(place?.width ?? 0);
  useLayoutEffect(() => {
    const holder = ref.current?.offsetParent as HTMLElement | null | undefined;
    if (!dockSide || !holder) return undefined;
    holder.classList.add(DOCK_CLASS[dockSide]);
    holder.style.setProperty(DOCK_WIDTH_VAR, `${dockWidth}px`);
    return () => {
      holder.classList.remove(DOCK_CLASS[dockSide]);
      holder.style.removeProperty(DOCK_WIDTH_VAR);
    };
  }, [dockSide, dockWidth]);

  return { ref, place: open ? place : null };
}
