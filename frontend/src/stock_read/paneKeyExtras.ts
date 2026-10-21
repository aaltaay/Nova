/**
 * Sections another layer on a chart pane adds to that pane's Key (Ahead's zone, ADR 065), while it draws. In memory,
 * per chart: the layer publishes its section under its own name and takes it back (`null`) when it stops drawing; the
 * pane's Key lists them first, before the stock read's own. Nothing is persisted.
 */
import { useSyncExternalStore } from 'react';
import type { IChartApi } from 'lightweight-charts';
import type { KeySection } from './paneKeyRows';

interface Board {
  sources: Map<string, KeySection>;
  snapshot: KeySection[];
}

const boards = new WeakMap<IChartApi, Board>();
const listeners = new Set<() => void>();
const NONE: KeySection[] = [];

/** Add (or replace) `source`'s section on `chart`'s Key; `null` takes it back. */
export function publishPaneKeySection(chart: IChartApi, source: string, section: KeySection | null): void {
  let b = boards.get(chart);
  if (!b) {
    if (section === null) return;
    b = { sources: new Map(), snapshot: NONE };
    boards.set(chart, b);
  }
  if ((b.sources.get(source) ?? null) === section) return;
  if (section) b.sources.set(source, section);
  else b.sources.delete(source);
  b.snapshot = [...b.sources.values()];
  for (const fn of [...listeners]) fn();
}

export function paneKeySections(chart: IChartApi | null | undefined): KeySection[] {
  return (chart && boards.get(chart)?.snapshot) || NONE;
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** The sections other layers have added to `chart`'s Key. */
export function usePaneKeySections(chart: IChartApi | null | undefined): KeySection[] {
  return useSyncExternalStore(subscribe, () => paneKeySections(chart));
}
