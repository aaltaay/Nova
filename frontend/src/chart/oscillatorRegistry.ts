/**
 * Which oscillator panes (MACD, RSI) hang under a price chart right now, and their own chart and main line, so
 * something drawn on the price pane can draw its part on the oscillator's too (Ahead's MACD fan, ADR 061). The
 * oscillator pane publishes itself when its series exist and takes itself back when it goes; a reader subscribes
 * per parent chart and hears the current handle at once. In memory, per chart; nothing is persisted.
 */
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

export type OscillatorKind = 'macd' | 'rsi';

export interface OscillatorPaneHandle {
  kind: OscillatorKind;
  /** The oscillator pane's own chart (its logical range follows the parent's). */
  chart: IChartApi;
  /** The MACD line (or the RSI line) series. */
  line: ISeriesApi<'Line'>;
}

type Listener = (h: OscillatorPaneHandle | null) => void;

interface Board {
  handles: Map<OscillatorKind, OscillatorPaneHandle>;
  listeners: Map<OscillatorKind, Set<Listener>>;
}

const boards = new WeakMap<IChartApi, Board>();

function boardOf(parent: IChartApi): Board {
  let b = boards.get(parent);
  if (!b) {
    b = { handles: new Map(), listeners: new Map() };
    boards.set(parent, b);
  }
  return b;
}

/** The pane under `parent` of `kind` (null: it went away). Listeners hear it only when it changed. */
export function publishOscillatorPane(parent: IChartApi, kind: OscillatorKind, h: OscillatorPaneHandle | null): void {
  const b = boardOf(parent);
  const was = b.handles.get(kind) ?? null;
  if (was === h || (was && h && was.chart === h.chart && was.line === h.line)) return;
  if (h) b.handles.set(kind, h);
  else b.handles.delete(kind);
  for (const fn of [...(b.listeners.get(kind) ?? [])]) fn(h);
}

/** The pane of `kind` under `parent` now (null when none). */
export function oscillatorPane(parent: IChartApi | null, kind: OscillatorKind): OscillatorPaneHandle | null {
  return parent ? boards.get(parent)?.handles.get(kind) ?? null : null;
}

/** Hear the pane of `kind` under `parent`: once at once with what is there, then on every change. */
export function subscribeOscillatorPane(parent: IChartApi | null, kind: OscillatorKind, cb: Listener): () => void {
  if (!parent) {
    cb(null);
    return () => {};
  }
  const b = boardOf(parent);
  let set = b.listeners.get(kind);
  if (!set) {
    set = new Set();
    b.listeners.set(kind, set);
  }
  set.add(cb);
  cb(b.handles.get(kind) ?? null);
  return () => {
    set?.delete(cb);
  };
}
