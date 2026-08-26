/**
 * ADR 015 — deciding when a pane must rebuild its drawings, and rebuilding them.
 *
 * Kept out of `useChartDrawingManager` so the decision rule is unit-testable
 * without a live lightweight-charts instance.
 */
import { ToolRegistry, type IDrawing, type SerializedDrawing } from 'lightweight-charts-drawing';
import type { ISeriesApi, Time } from 'lightweight-charts';
import {
  buildSeriesTimeIndex,
  snapDrawingToSeries,
  type SeriesTimeIndex,
} from './chartDrawingTime';

/** What a pane hydrated from last time. */
export interface HydrateState {
  symbol: string;
  revision: number;
  hadBars: boolean;
}

export interface HydrateTarget {
  symbol: string;
  revision: number;
  hasBars: boolean;
}

/**
 * A pane rebuilds on a symbol switch (so AAPL levels never bleed onto TSLA), on
 * a store change it did not produce, and once bars first arrive — the first
 * hydrate of an empty pane cannot snap anchors to a grid that does not exist yet.
 * Anything else is this pane's own echo, and rebuilding would drop the selection
 * the operator is holding.
 */
export function shouldHydrateDrawings(
  prev: HydrateState | null,
  next: HydrateTarget,
): boolean {
  if (!prev) return true;
  if (prev.symbol !== next.symbol) return true;
  if (prev.revision !== next.revision) return true;
  return !prev.hadBars && next.hasBars;
}

/** Rebuild a `SerializedDrawing` into a live drawing via the library registry. */
export function drawingFactory(type: string, data: SerializedDrawing): IDrawing | null {
  try {
    return ToolRegistry.getInstance().createDrawing(
      type,
      data.id,
      data.anchors,
      data.style,
      data.options,
    );
  } catch {
    return null;
  }
}

/** This pane's painted bar times, as a snap index. */
export function seriesTimeIndex(
  series: ISeriesApi<'Candlestick'> | null | undefined,
): SeriesTimeIndex {
  if (!series) return buildSeriesTimeIndex([]);
  try {
    return buildSeriesTimeIndex(series.data().map((bar) => bar.time as Time));
  } catch {
    return buildSeriesTimeIndex([]);
  }
}

export function snapAll(
  stored: readonly SerializedDrawing[],
  index: SeriesTimeIndex,
): SerializedDrawing[] {
  return stored.map((drawing) => snapDrawingToSeries(drawing, index));
}
