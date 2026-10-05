/**
 * The words a chart pane has drawn over its candles, so something that floats over a candle can keep clear of
 * them (operator report 2026-10-05: the close countdown sat on top of the setup's "5m ... +83.3%" label).
 * Each primitive that writes words on the pane -- the stock read's labels, pins and edge column, the fill
 * arrows' prices -- publishes the rectangles it drew (media pixels, the pane's own space), and the countdown
 * chip, which knows only the candle, picks a spot that touches none of them. In memory, per chart; nothing is
 * persisted.
 *
 * Draw order between two primitives is not something to lean on, so a change is announced after the paint
 * that made it (a microtask): a reader that drew before the publisher used the previous paint's words, sees
 * the version it used is old, and asks for one more paint. A reader that drew after finds nothing to do.
 */
import type { IChartApi } from 'lightweight-charts';

export interface PaneWordRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Board {
  sources: Map<string, PaneWordRect[]>;
  version: number;
  snapshot: { rects: readonly PaneWordRect[]; version: number } | null;
  listeners: Set<() => void>;
  announcing: boolean;
}

const boards = new WeakMap<IChartApi, Board>();
const NONE: { rects: readonly PaneWordRect[]; version: number } = { rects: [], version: 0 };

function boardOf(chart: IChartApi): Board {
  let b = boards.get(chart);
  if (!b) {
    b = { sources: new Map(), version: 0, snapshot: null, listeners: new Set(), announcing: false };
    boards.set(chart, b);
  }
  return b;
}

/** Tenths of a pixel: a layout that did not move hashes the same, float noise does not count as a change. */
function tenth(n: number): number {
  return Math.round(n * 10) / 10;
}

function same(a: PaneWordRect[] | undefined, b: PaneWordRect[]): boolean {
  if (!a || a.length !== b.length) return false;
  return a.every((r, i) => r.left === b[i].left && r.top === b[i].top && r.right === b[i].right
    && r.bottom === b[i].bottom);
}

function announce(b: Board): void {
  if (b.announcing) return;
  b.announcing = true;
  queueMicrotask(() => {
    b.announcing = false;
    for (const fn of [...b.listeners]) fn();
  });
}

/** `source`'s words on `chart`, replacing what it published before (an empty list takes them back). */
export function publishPaneWords(chart: IChartApi, source: string, rects: readonly PaneWordRect[]): void {
  const b = boardOf(chart);
  const next = rects.map(r => ({ left: tenth(r.left), top: tenth(r.top), right: tenth(r.right),
    bottom: tenth(r.bottom) }));
  if (same(b.sources.get(source), next) || (next.length === 0 && !b.sources.has(source))) return;
  if (next.length) b.sources.set(source, next);
  else b.sources.delete(source);
  b.version += 1;
  b.snapshot = null;
  announce(b);
}

/** Everything published on `chart`, with a version that changes whenever any of it does. */
export function paneWords(chart: IChartApi | null): { rects: readonly PaneWordRect[]; version: number } {
  const b = chart ? boards.get(chart) : undefined;
  if (!b) return NONE;
  if (!b.snapshot) b.snapshot = { rects: [...b.sources.values()].flat(), version: b.version };
  return b.snapshot;
}

/** Called once after the paint that changed `chart`'s words; the returned function stops it. */
export function subscribePaneWords(chart: IChartApi | null, fn: () => void): () => void {
  if (!chart) return () => {};
  const b = boardOf(chart);
  b.listeners.add(fn);
  return () => {
    b.listeners.delete(fn);
  };
}
