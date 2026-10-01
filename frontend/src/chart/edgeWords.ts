/**
 * The words a chart pane writes at its right edge, and who lays them out (operator report 2026-09-30:
 * "everything is getting on top of each other in the charts!"). On its own each line's series carries its
 * title (the EMAs' and VWAP's tags), which lightweight-charts draws at the edge by itself. A pane whose stock
 * read draws its levels there claims the edge: the series drop their titles and publish their words here
 * instead, the position tag says where it sits, and the claimant places them all with its own in one column,
 * so none covers another. In memory, per chart; nothing is persisted.
 */
import type { IChartApi, ISeriesApi, SeriesType } from 'lightweight-charts';

/** How firmly a word keeps its place when the column crowds: the least important go first. */
export const EDGE_PRIORITY = {
  planLine: 100,
  vwap: 80,
  highOfDay: 70,
  level: 60,
  ema: 50,
  offView: 40,
} as const;

/** The EMAs' order in a crowd: the 9 (momentum's line) before the 20, the 20 before the 200. */
export function emaPriority(length: number): number {
  return EDGE_PRIORITY.ema + (length <= 9 ? 2 : length <= 20 ? 1 : 0);
}

/** A line's tag: placed at the line's value on the pane's last visible bar, as a series title is. */
export interface EdgeWord {
  id: string;
  text: string;
  color: string;
  priority: number;
  series: ISeriesApi<SeriesType>;
  /** Out of view its tag adds the value ("↑ 200 EMA 7.31"); false when the text already says it. */
  valueWhenOff: boolean;
}

/** Room at the edge something else holds (the position tag), never covered. */
export interface EdgeReserve {
  id: string;
  price: number;
  /** Its height in pixels, centred on the price. */
  height: number;
}

interface Board {
  claims: number;
  words: Map<string, EdgeWord[]>;
  reserves: Map<string, EdgeReserve[]>;
  listeners: Set<() => void>;
  snapshot: { words: EdgeWord[]; reserves: EdgeReserve[] } | null;
}

const boards = new WeakMap<IChartApi, Board>();
const NONE = { words: [] as EdgeWord[], reserves: [] as EdgeReserve[] };

function boardOf(chart: IChartApi): Board {
  let b = boards.get(chart);
  if (!b) {
    b = { claims: 0, words: new Map(), reserves: new Map(), listeners: new Set(), snapshot: null };
    boards.set(chart, b);
  }
  return b;
}

function emit(b: Board): void {
  b.snapshot = null;
  for (const fn of [...b.listeners]) fn();
}

function sameWords(a: EdgeWord[] | undefined, b: EdgeWord[]): boolean {
  if (!a || a.length !== b.length) return false;
  return a.every((w, i) => w.id === b[i].id && w.text === b[i].text && w.color === b[i].color
    && w.priority === b[i].priority && w.series === b[i].series && w.valueWhenOff === b[i].valueWhenOff);
}

function sameReserves(a: EdgeReserve[] | undefined, b: EdgeReserve[]): boolean {
  if (!a || a.length !== b.length) return false;
  return a.every((r, i) => r.id === b[i].id && r.price === b[i].price && r.height === b[i].height);
}

/** `source`'s words on `chart`, replacing what it published before (an empty list takes them back). */
export function publishEdgeWords(chart: IChartApi, source: string, words: EdgeWord[]): void {
  const b = boardOf(chart);
  if (sameWords(b.words.get(source), words) || (words.length === 0 && !b.words.has(source))) return;
  if (words.length) b.words.set(source, words);
  else b.words.delete(source);
  emit(b);
}

/** `source`'s room on `chart`, replacing what it held before (an empty list gives it back). */
export function publishEdgeReserves(chart: IChartApi, source: string, reserves: EdgeReserve[]): void {
  const b = boardOf(chart);
  if (sameReserves(b.reserves.get(source), reserves) || (reserves.length === 0 && !b.reserves.has(source))) return;
  if (reserves.length) b.reserves.set(source, reserves);
  else b.reserves.delete(source);
  emit(b);
}

/** Lay out `chart`'s edge from now on; the returned function hands it back. */
export function claimEdge(chart: IChartApi): () => void {
  const b = boardOf(chart);
  b.claims += 1;
  if (b.claims === 1) emit(b);
  let done = false;
  return () => {
    if (done) return;
    done = true;
    b.claims -= 1;
    if (b.claims === 0) emit(b);
  };
}

/** Whether something lays out `chart`'s edge: the series then leave their titles to it. */
export function edgeClaimed(chart: IChartApi | null): boolean {
  return chart ? (boards.get(chart)?.claims ?? 0) > 0 : false;
}

/** Everything published on `chart`; the same object until something changes. */
export function edgeContents(chart: IChartApi | null): { words: EdgeWord[]; reserves: EdgeReserve[] } {
  const b = chart ? boards.get(chart) : undefined;
  if (!b) return NONE;
  if (!b.snapshot) b.snapshot = { words: [...b.words.values()].flat(), reserves: [...b.reserves.values()].flat() };
  return b.snapshot;
}

/** Called on every change to `chart`'s edge (a claim, words, room); the returned function stops it. */
export function subscribeEdge(chart: IChartApi | null, fn: () => void): () => void {
  if (!chart) return () => {};
  const b = boardOf(chart);
  b.listeners.add(fn);
  return () => {
    b.listeners.delete(fn);
  };
}
