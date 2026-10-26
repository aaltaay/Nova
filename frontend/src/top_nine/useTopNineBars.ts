/**
 * One tile's 1-minute candles: the Trader's own bars (`/api/ticker/{symbol}/bars`, store-first on the
 * backend, ADR 012) through the shared bars store, asked again every CHART_REFETCH_SEC like the
 * Trader's 1-minute pane. A full day is asked for so the session VWAP anchors at 04:00 ET. No Level 1
 * or tape line is opened for a tile: the candles move when the store's bars do.
 */
import { useEffect, useMemo, useState } from 'react';
import { CHART_REFETCH_SEC, CHART_TIMEFRAME_BAR_LIMITS } from '../constants';
import { ensureBars, getBarsEntry, sessionVwapPoints, subscribeBars, type VwapPoint } from '../chart';
import { rawBarsToIndicatorBars, type IndicatorBar } from '../chartIndicators';
import type { RawBar } from '../tickerChartData';
import { TOP_NINE_TIMEFRAME } from './topNineConstants';

export interface TopNineBars {
  bars: IndicatorBar[];
  vwap: VwapPoint[];
  error: string | null;
  loaded: boolean;
}

const EMPTY: RawBar[] = [];

export function useTopNineBars(symbol: string): TopNineBars {
  const [raw, setRaw] = useState<RawBar[]>(() => getBarsEntry(symbol, TOP_NINE_TIMEFRAME)?.bars ?? EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(() => getBarsEntry(symbol, TOP_NINE_TIMEFRAME) != null);

  useEffect(() => {
    const read = () => {
      const entry = getBarsEntry(symbol, TOP_NINE_TIMEFRAME);
      setRaw(entry?.bars ?? EMPTY);
      if (entry) setLoaded(true);
    };
    read();
    const unsub = subscribeBars(symbol, TOP_NINE_TIMEFRAME, read);
    const controller = new AbortController();
    const fetchNow = () => {
      ensureBars(symbol, TOP_NINE_TIMEFRAME, controller.signal, CHART_TIMEFRAME_BAR_LIMITS[TOP_NINE_TIMEFRAME])
        .then(() => setError(null))
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === 'AbortError') return;
          setError(err instanceof Error ? err.message : String(err));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoaded(true);
        });
    };
    fetchNow();
    const timer = window.setInterval(fetchNow, (CHART_REFETCH_SEC[TOP_NINE_TIMEFRAME] ?? 30) * 1000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
      unsub();
    };
  }, [symbol]);

  return useMemo(() => {
    const bars = rawBarsToIndicatorBars(raw, TOP_NINE_TIMEFRAME);
    return { bars, vwap: sessionVwapPoints(bars), error, loaded };
  }, [raw, error, loaded]);
}
