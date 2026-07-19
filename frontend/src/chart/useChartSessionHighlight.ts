/** Attach shared session-band primitive to the candle series (all TickerChart variants). */

import { useEffect, useRef } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { SessionHighlightingPrimitive } from './SessionHighlightingPrimitive';
import { supportsSessionHighlight } from './sessionHighlight';

interface Options {
  /** Non-null once useChartInstance has created the chart (triggers attach). */
  chartApi: IChartApi | null;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  timeframe: string;
  /** Bump when bars reload so colors rebuild after setData. */
  barsRevision: number;
}

export function useChartSessionHighlight({
  chartApi,
  candleSeriesRef,
  timeframe,
  barsRevision,
}: Options): boolean {
  const primitiveRef = useRef<SessionHighlightingPrimitive | null>(null);
  const enabled = supportsSessionHighlight(timeframe);

  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chartApi || !series || !enabled) {
      return;
    }

    const primitive = new SessionHighlightingPrimitive();
    series.attachPrimitive(primitive);
    primitiveRef.current = primitive;
    primitive.refresh();

    return () => {
      try {
        series.detachPrimitive(primitive);
      } catch {
        /* chart/series already gone */
      }
      if (primitiveRef.current === primitive) {
        primitiveRef.current = null;
      }
    };
  }, [chartApi, candleSeriesRef, enabled, timeframe]);

  useEffect(() => {
    if (!enabled) return;
    primitiveRef.current?.refresh();
  }, [barsRevision, enabled]);

  return enabled;
}
