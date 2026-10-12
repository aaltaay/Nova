/**
 * Which card the pointer gets when a drawing and a candle are both under it (operator report 2026-10-12: resting
 * on a candle inside a failed setup's red box only ever showed the box's story, "if I'm specifically highlighting
 * a candle, I do care about the candle information more than anything else"). A drawing that covers an area -- a
 * setup's box -- says so in its hover id (`areaHoverId`); a drawing hit at a point -- a label, a ring, a trend
 * line, an axis tick -- does not. Over an area the candle under the pointer wins: its card opens after the usual
 * rest (`useCandleHover`) and the area's own card steps aside while it is open (`useCandleCardOpen`). Over a
 * point drawing the drawing's card wins, as before. In memory, per chart; nothing is persisted.
 */
import { useCallback, useSyncExternalStore } from 'react';
import type { IChartApi } from 'lightweight-charts';

const AREA_PREFIX = 'area:';

/** `id` as the hover of a drawing that covers an area, where a candle under the pointer wins. */
export function areaHoverId(id: string): string {
  return `${AREA_PREFIX}${id}`;
}

export interface HoverTarget {
  /** The drawing's own hover id, without the area mark. */
  id: string;
  /** Over the drawing's area (a setup's box) rather than a label or a mark it drew. */
  area: boolean;
}

/** The drawing a crosshair event's `hoveredObjectId` names; null over none. */
export function hoverTarget(hoveredObjectId: unknown): HoverTarget | null {
  if (hoveredObjectId == null) return null;
  const raw = String(hoveredObjectId);
  return raw.startsWith(AREA_PREFIX) ? { id: raw.slice(AREA_PREFIX.length), area: true } : { id: raw, area: false };
}

interface Board {
  open: boolean;
  listeners: Set<() => void>;
}

const boards = new WeakMap<IChartApi, Board>();

function boardOf(chart: IChartApi): Board {
  let b = boards.get(chart);
  if (!b) {
    b = { open: false, listeners: new Set() };
    boards.set(chart, b);
  }
  return b;
}

/** Whether the candle card is open on `chart`; only `useCandleHover` says so. */
export function setCandleCardOpen(chart: IChartApi, open: boolean): void {
  const b = boardOf(chart);
  if (b.open === open) return;
  b.open = open;
  for (const fn of [...b.listeners]) fn();
}

/** True while the candle card is open on `chart`. */
export function useCandleCardOpen(chart: IChartApi | null): boolean {
  const subscribe = useCallback((fn: () => void) => {
    if (!chart) return () => {};
    const b = boardOf(chart);
    b.listeners.add(fn);
    return () => {
      b.listeners.delete(fn);
    };
  }, [chart]);
  const read = useCallback(() => (chart ? boards.get(chart)?.open ?? false : false), [chart]);
  return useSyncExternalStore(subscribe, read, read);
}
