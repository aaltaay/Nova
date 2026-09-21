/**
 * Publishes one price line per price-level drawing, purely to put its price on
 * the price axis (see `chartDrawingAxisLabel.ts` for why the library's own
 * in-plot label is off).
 *
 * Driven by the drawings store rather than by manager events, so every pane of
 * the symbol shows the same chips and a remount rebuilds them: the store is
 * updated synchronously on add/move/remove (only its PUT is debounced), so the
 * chip tracks a drag closely enough and is exact on release.
 */
import { useEffect, useRef, useState } from 'react';
import type { IPriceLine, ISeriesApi } from 'lightweight-charts';
import {
  diffAxisLevels,
  drawingAxisLevels,
  drawingAxisLineOptions,
  type DrawingAxisLevel,
} from './chartDrawingAxisLabel';
import { drawingsKey, getDrawings, subscribeDrawings } from './chartDrawingsStore';

interface Args {
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  symbol: string;
  /** Bumps when the pane repaints its series, which discards its price lines. */
  seriesRevision?: number;
}

export function useChartDrawingAxisLabels({ candleSeriesRef, symbol, seriesRevision }: Args): void {
  const [storeTick, setStoreTick] = useState(0);
  const linesRef = useRef(new Map<string, IPriceLine>());
  const levelsRef = useRef(new Map<string, DrawingAxisLevel>());

  const key = drawingsKey(symbol);
  useEffect(() => {
    if (!key) return undefined;
    return subscribeDrawings(key, () => setStoreTick(tick => tick + 1));
  }, [key]);

  // A new series owns no price lines, so drop the stale handles rather than
  // calling removePriceLine on a series that never had them.
  useEffect(() => {
    linesRef.current = new Map();
    levelsRef.current = new Map();
  }, [seriesRevision, symbol]);

  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    const next = key ? drawingAxisLevels(getDrawings(key)) : new Map<string, DrawingAxisLevel>();
    const { added, changed, removed } = diffAxisLevels(levelsRef.current, next);
    try {
      for (const id of removed) {
        const line = linesRef.current.get(id);
        if (line) series.removePriceLine(line);
        linesRef.current.delete(id);
      }
      for (const id of changed) {
        linesRef.current.get(id)?.applyOptions(drawingAxisLineOptions(next.get(id)!));
      }
      for (const id of added) {
        linesRef.current.set(id, series.createPriceLine(drawingAxisLineOptions(next.get(id)!)));
      }
      levelsRef.current = next;
    } catch {
      // Series disposed between render and effect; the next paint rebuilds.
      linesRef.current = new Map();
      levelsRef.current = new Map();
    }
  }, [candleSeriesRef, key, storeTick, seriesRevision]);

  useEffect(() => () => {
    const series = candleSeriesRef.current;
    if (series) {
      for (const line of linesRef.current.values()) {
        try { series.removePriceLine(line); } catch { /* already disposed */ }
      }
    }
    linesRef.current = new Map();
    levelsRef.current = new Map();
  }, [candleSeriesRef]);
}
