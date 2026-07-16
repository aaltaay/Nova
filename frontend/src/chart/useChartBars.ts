/** ADR 005 — REST bar loading with request versioning and stale-response rejection. */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  CandlestickData,
  HistogramData,
  IChartApi,
  ISeriesApi,
  Time,
} from 'lightweight-charts';
import {
  API_BASE_URL,
  CHART_BARS_FETCH_TIMEOUT_MS,
  CHART_MOCK_BAR_COUNT,
  CHART_MOCK_BASE_PRICE,
  CHART_REFETCH_SEC,
} from '../constants';
import {
  rawBarsToIndicatorBars,
  type IndicatorBar,
} from '../chartIndicators';
import {
  buildMockBars,
  isoToEtTime,
  type RawBar,
} from '../tickerChartData';
import { useWorkspace } from '../workspace';
import { allowMockBarsFallback, emptyBarsMessage } from './chartBarsPolicy';
import { isCurrentBarsRequest } from './requestVersion';
import type { ChartTradeUpdate } from './types';

const API_URL = `${API_BASE_URL}/api`;

interface UseChartBarsOptions {
  symbol: string;
  timeframe: string;
  chartRef: React.RefObject<IChartApi | null>;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  volSeriesRef: React.RefObject<ISeriesApi<'Histogram'> | null>;
  lastCandleRef: React.RefObject<CandlestickData<Time> | null>;
  lastTrade: ChartTradeUpdate | null | undefined;
  applyLiveTrade: (trade: ChartTradeUpdate, tf: string) => void;
  onSeriesReset: () => void;
}

export function useChartBars({
  symbol,
  timeframe,
  chartRef,
  candleSeriesRef,
  volSeriesRef,
  lastCandleRef,
  lastTrade,
  applyLiveTrade,
  onSeriesReset,
}: UseChartBarsOptions) {
  const { discoveryProvider } = useWorkspace();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usingMock, setUsingMock] = useState(false);
  const [indicatorBars, setIndicatorBars] = useState<IndicatorBar[]>([]);

  const barsRequestVersionRef = useRef(0);
  const lastTradeRef = useRef<ChartTradeUpdate | null | undefined>(lastTrade);

  useEffect(() => {
    lastTradeRef.current = lastTrade;
  }, [lastTrade]);

  const fetchBars = useCallback(async (sym: string, tf: string, background = false) => {
    const requestVersion = ++barsRequestVersionRef.current;
    if (!background) {
      setLoading(true);
      setError(null);
    }
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), CHART_BARS_FETCH_TIMEOUT_MS);
    try {
      const res = await fetch(`${API_URL}/ticker/${sym}/bars?timeframe=${tf}`, {
        signal: controller.signal,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const data = (await res.json()) as { bars: RawBar[] };
      if (!isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current)) return;
      let bars = data.bars ?? [];
      let mock = false;
      if (bars.length === 0) {
        if (!allowMockBarsFallback(discoveryProvider)) {
          setUsingMock(false);
          setIndicatorBars([]);
          candleSeriesRef.current?.setData([]);
          volSeriesRef.current?.setData([]);
          lastCandleRef.current = null;
          setError(emptyBarsMessage(discoveryProvider));
          return;
        }
        bars = buildMockBars(CHART_MOCK_BAR_COUNT, CHART_MOCK_BASE_PRICE);
        mock = true;
      }
      setUsingMock(mock);
      const daily = tf === '1Day' || tf === '1Week' || tf === '1Month';

      const candles: CandlestickData<Time>[] = bars.map(b => ({
        time: isoToEtTime(b.t, daily),
        open: b.o, high: b.h, low: b.l, close: b.c,
      }));
      const volumes: HistogramData<Time>[] = bars.map(b => ({
        time: isoToEtTime(b.t, daily),
        value: b.v,
        color: b.c >= b.o ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)',
      }));

      candleSeriesRef.current?.setData(candles);
      volSeriesRef.current?.setData(volumes);
      lastCandleRef.current = candles.length > 0 ? candles[candles.length - 1] : null;
      setIndicatorBars(rawBarsToIndicatorBars(bars, tf));
      if (!background && candles.length > 0) chartRef.current?.timeScale().fitContent();
      if (background) {
        setError(null);
        const liveTrade = lastTradeRef.current;
        if (liveTrade?.price && liveTrade.timestamp) applyLiveTrade(liveTrade, tf);
      }
    } catch (err) {
      if (isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current) && !background) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setError('Chart bars timed out — IBKR historical may be busy. Try again.');
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load chart');
        }
      }
    } finally {
      window.clearTimeout(timeoutId);
      if (isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current) && !background) {
        setLoading(false);
      }
    }
  }, [
    applyLiveTrade,
    candleSeriesRef,
    chartRef,
    discoveryProvider,
    lastCandleRef,
    volSeriesRef,
  ]);

  useEffect(() => {
    onSeriesReset();
    void fetchBars(symbol, timeframe, false);
    return () => {
      barsRequestVersionRef.current += 1;
    };
  }, [symbol, timeframe, fetchBars, onSeriesReset]);

  useEffect(() => {
    const sec = CHART_REFETCH_SEC[timeframe];
    if (!sec) return;
    const id = setInterval(() => fetchBars(symbol, timeframe, true), sec * 1000);
    return () => clearInterval(id);
  }, [symbol, timeframe, fetchBars]);

  return { loading, error, usingMock, indicatorBars };
}
