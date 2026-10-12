/**
 * Drag the operator's own entry or stop on the 1-minute chart (ADR 036; a short's entry and buy stop, ADR 048).
 * Only a hand plan moves -- a setup's levels are the scanner's. The pointer grabs a line within a few pixels of it; while it
 * drags, `preview` holds the moving levels (each target keeps its distance from the entry); on release the plan is
 * the operator's new entry and stop, and the backend reads the menu's targets afresh from the new entry (#845).
 * A press anywhere else is the chart's, untouched.
 */
import { useEffect, useRef, useState, type RefObject } from 'react';
import type { ISeriesApi } from 'lightweight-charts';
import type { StockPlan } from './types';

const GRAB_PX = 5;

export interface DragPreview {
  entry: number;
  stop: number;
}

function roundPx(p: number): number {
  const step = Math.abs(p) < 1 ? 0.0001 : 0.01;
  return Math.round(p / step) * step;
}

/** The plan with a dragged entry and stop while it moves: each target keeps its distance from the entry (target 2
 * too; a short's covers under it), and the R each is measured in follows the new risk. The targets' prices and
 * reasons are the backend's once the drag is let go -- a preview never invents a level. */
export function draggedPlan(plan: StockPlan, d: DragPreview): StockPlan {
  const risk = Math.abs(d.entry - d.stop);
  const shift = plan.entry !== null ? d.entry - plan.entry : 0;
  const moved = (p: number | null | undefined) => (p == null ? null : p + shift);
  const target = moved(plan.target);
  const target2 = moved(plan.target2);
  const reward = target === null ? null : Math.abs(target - d.entry);
  const reward2 = target2 === null ? null : Math.abs(target2 - d.entry);
  const inR = (r: number | null) => (r === null || !(risk > 0) ? null : r / risk);
  return {
    ...plan, entry: d.entry, stop: d.stop, target, target2, risk, reward, rr: inR(reward), reward2, rr2: inR(reward2),
  };
}

export function usePlanDrag({
  containerRef,
  series,
  plan,
  enabled,
  onCommit,
}: {
  containerRef: RefObject<HTMLElement | null>;
  series: ISeriesApi<'Candlestick'> | null;
  plan: StockPlan | null;
  enabled: boolean;
  onCommit: (entry: number, stop: number) => void;
}): DragPreview | null {
  const [preview, setPreview] = useState<DragPreview | null>(null);
  const commit = useRef(onCommit);
  commit.current = onCommit;
  const entry = plan?.entry ?? null;
  const stop = plan?.stop ?? null;
  // A short's buy stop stays over its entry (ADR 048); a long's stop under it.
  const short = plan?.side === 'short';

  // A new read with the committed levels ends the preview.
  useEffect(() => setPreview(null), [entry, stop]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !series || !enabled || entry === null || stop === null) return;
    let dragging: 'entry' | 'stop' | null = null;
    let current: DragPreview = { entry, stop };
    const yOf = (e: PointerEvent) => e.clientY - el.getBoundingClientRect().top;
    const near = (y: number): 'entry' | 'stop' | null => {
      const ye = series.priceToCoordinate(current.entry);
      const ys = series.priceToCoordinate(current.stop);
      if (ye !== null && Math.abs(y - ye) <= GRAB_PX) return 'entry';
      if (ys !== null && Math.abs(y - ys) <= GRAB_PX) return 'stop';
      return null;
    };
    const onMove = (e: PointerEvent) => {
      if (!dragging) {
        el.style.cursor = near(yOf(e)) ? 'ns-resize' : '';
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      const price = series.coordinateToPrice(yOf(e));
      if (price === null || !(price > 0)) return;
      const p = roundPx(price);
      const tick = Math.abs(p) < 1 ? 0.0001 : 0.01;
      current = dragging === 'entry'
        ? { entry: short ? Math.min(p, current.stop - tick) : Math.max(p, current.stop + tick), stop: current.stop }
        : { entry: current.entry, stop: short ? Math.max(p, current.entry + tick) : Math.min(p, current.entry - tick) };
      setPreview({ ...current });
    };
    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      const hit = near(yOf(e));
      if (!hit) return;
      dragging = hit;
      e.preventDefault();
      e.stopPropagation();
      el.setPointerCapture?.(e.pointerId);
    };
    const onUp = (e: PointerEvent) => {
      if (!dragging) return;
      dragging = null;
      e.preventDefault();
      e.stopPropagation();
      el.releasePointerCapture?.(e.pointerId);
      el.style.cursor = '';
      commit.current(current.entry, current.stop);
    };
    // The chart pans on mouse events too: while a line is held they never reach it.
    const onMouse = (e: MouseEvent) => {
      if (!dragging) return;
      e.preventDefault();
      e.stopPropagation();
    };
    const listeners: [string, EventListener][] = [
      ['pointermove', onMove as EventListener],
      ['pointerdown', onDown as EventListener],
      ['pointerup', onUp as EventListener],
      ['pointercancel', onUp as EventListener],
      ['mousedown', onMouse as EventListener],
      ['mousemove', onMouse as EventListener],
    ];
    for (const [type, fn] of listeners) el.addEventListener(type, fn, true);
    return () => {
      for (const [type, fn] of listeners) el.removeEventListener(type, fn, true);
      el.style.cursor = '';
    };
  }, [containerRef, series, enabled, entry, stop, short]);

  return preview;
}
