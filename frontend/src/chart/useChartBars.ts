/** ADR 005 -- REST bar loading via shared barsStore; incremental series updates. */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  CandlestickData,
  IChartApi,
  ISeriesApi,
  Time,
} from 'lightweight-charts';
import {
  CHART_BARS_CLIENT_STALE_MS,
  CHART_BARS_ERROR_RETRY_MAX,
  CHART_BARS_ERROR_RETRY_MS,
  CHART_MOCK_BAR_COUNT,
  CHART_MOCK_BASE_PRICE,
  CHART_REFETCH_SEC,
  CHART_TIMEFRAME_BAR_LIMITS,
} from '../constants';
import {
  rawBarsToIndicatorBars,
  type IndicatorBar,
} from '../chartIndicators';
import {
  buildMockBars,
  canIncrementalBarsUpdate,
  rawBarsToSeries,
  type RawBar,
} from '../tickerChartData';
import { useWorkspace } from '../workspace';
import { allowMockBarsFallback, emptyBarsMessage } from './chartBarsPolicy';
import {
  ensureBars,
  getBarsEntry,
  isBarsEntryFresh,
  subscribeBars,
} from './barsStore';
import { shouldScheduleBarsErrorRetry } from './barsErrorRetry';
import { isCurrentBarsRequest } from './requestVersion';
import type { ChartTradeUpdate } from './types';

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
  /** When false, pause polling and skip network (hidden Trader tab). */
  chartActive?: boolean;
}

function paintFull(
  candles: CandlestickData<Time>[],
  volumes: ReturnType<typeof rawBarsToSeries>['volumes'],
  candleSeriesRef: UseChartBarsOptions['candleSeriesRef'],
  volSeriesRef: UseChartBarsOptions['volSeriesRef'],
  chartRef: UseChartBarsOptions['chartRef'],
  fitContent: boolean,
): void {
  candleSeriesRef.current?.setData(candles);
  volSeriesRef.current?.setData(volumes);
  if (fitContent && candles.length > 0) chartRef.current?.timeScale().fitContent();
}

function paintBars(
  bars: RawBar[],
  tf: string,
  candleSeriesRef: UseChartBarsOptions['candleSeriesRef'],
  volSeriesRef: UseChartBarsOptions['volSeriesRef'],
  lastCandleRef: UseChartBarsOptions['lastCandleRef'],
  chartRef: UseChartBarsOptions['chartRef'],
  prevBars: RawBar[] | null,
  fitContent: boolean,
): IndicatorBar[] {
  const { candles, volumes } = rawBarsToSeries(bars, tf);
  const canIncremental =
    prevBars != null
    && canIncrementalBarsUpdate(prevBars, bars)
    && candleSeriesRef.current
    && volSeriesRef.current
    && candles.length > 0;

  if (canIncremental) {
    // LWC update() only accepts the tip (same time replace) or a newer time.
    // Never update penultimate -- that throws "Cannot update oldest data".
    const tip = candles[candles.length - 1];
    const tipVol = volumes[volumes.length - 1];
    try {
      candleSeriesRef.current!.update(tip);
      volSeriesRef.current!.update(tipVol);
    } catch {
      paintFull(candles, volumes, candleSeriesRef, volSeriesRef, chartRef, fitContent);
    }
  } else {
    paintFull(candles, volumes, candleSeriesRef, volSeriesRef, chartRef, fitContent);
  }
  lastCandleRef.current = candles.length > 0 ? candles[candles.length - 1] : null;
  return rawBarsToIndicatorBars(bars, tf);
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
  chartActive = true,
}: UseChartBarsOptions) {
  const { discoveryProvider } = useWorkspace();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usingMock, setUsingMock] = useState(false);
  const [indicatorBars, setIndicatorBars] = useState<IndicatorBar[]>([]);

  const barsRequestVersionRef = useRef(0);
  const lastTradeRef = useRef<ChartTradeUpdate | null | undefined>(lastTrade);
  const paintedBarsRef = useRef<RawBar[] | null>(null);
  const chartActiveRef = useRef(chartActive);
  const errorRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const errorRetryCountRef = useRef(0);

  useEffect(() => {
    lastTradeRef.current = lastTrade;
  }, [lastTrade]);

  useEffect(() => {
    chartActiveRef.current = chartActive;
  }, [chartActive]);

  const clearErrorRetry = useCallback(() => {
    if (errorRetryTimerRef.current != null) {
      clearTimeout(errorRetryTimerRef.current);
      errorRetryTimerRef.current = null;
    }
  }, []);

  const applyStoreBars = useCallback((
    bars: RawBar[],
    opts: { background: boolean; fitContent: boolean },
  ) => {
    let next = bars;
    let mock = false;
    if (next.length === 0) {
      if (!allowMockBarsFallback(discoveryProvider)) {
        setUsingMock(false);
        setIndicatorBars([]);
        candleSeriesRef.current?.setData([]);
        volSeriesRef.current?.setData([]);
        lastCandleRef.current = null;
        paintedBarsRef.current = [];
        setError(emptyBarsMessage(discoveryProvider));
        return;
      }
      next = buildMockBars(CHART_MOCK_BAR_COUNT, CHART_MOCK_BASE_PRICE);
      mock = true;
    }
    setUsingMock(mock);
    const indicators = paintBars(
      next,
      timeframe,
      candleSeriesRef,
      volSeriesRef,
      lastCandleRef,
      chartRef,
      paintedBarsRef.current,
      opts.fitContent,
    );
    paintedBarsRef.current = next;
    setIndicatorBars(indicators);
    clearErrorRetry();
    setError(null);
    // Re-apply latest trade after any successful paint (foreground or background)
    // so a tip that arrived before the series was ready still merges.
    const liveTrade = lastTradeRef.current;
    if (liveTrade?.price && liveTrade.timestamp) applyLiveTrade(liveTrade, timeframe);
  }, [
    applyLiveTrade,
    candleSeriesRef,
    chartRef,
    clearErrorRetry,
    discoveryProvider,
    lastCandleRef,
    timeframe,
    volSeriesRef,
  ]);

  const fetchBars = useCallback(async (
    sym: string,
    tf: string,
    background = false,
    signal?: AbortSignal,
  ) => {
    const requestVersion = ++barsRequestVersionRef.current;
    if (!background) {
      setLoading(true);
      setError(null);
    }
    try {
      const limit = CHART_TIMEFRAME_BAR_LIMITS[tf];
      const bars = await ensureBars(sym, tf, signal, limit);
      if (!isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current)) return;
      applyStoreBars(bars, { background, fitContent: !background });
    } catch (err) {
      if (!isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current)) return;
      if (!background) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setError('Chart bars timed out -- IBKR historical may be busy. Try again.');
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load chart');
        }
      }
      if (shouldScheduleBarsErrorRetry({
        storeHasBars: Boolean(getBarsEntry(sym, tf)?.bars.length),
        retriesUsed: errorRetryCountRef.current,
        maxRetries: CHART_BARS_ERROR_RETRY_MAX,
        chartActive: chartActiveRef.current,
      })) {
        errorRetryCountRef.current += 1;
        clearErrorRetry();
        const jitter = Math.floor(Math.random() * 1000);
        errorRetryTimerRef.current = setTimeout(() => {
          errorRetryTimerRef.current = null;
          if (!chartActiveRef.current) return;
          if (getBarsEntry(sym, tf)?.bars.length) return;
          void fetchBars(sym, tf, true);
        }, CHART_BARS_ERROR_RETRY_MS + jitter);
      }
    } finally {
      if (isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current) && !background) {
        setLoading(false);
      }
    }
  }, [applyStoreBars, clearErrorRetry]);

  // Instant paint from shared store; subscribe for batch/warm updates.
  useEffect(() => {
    onSeriesReset();
    paintedBarsRef.current = null;
    errorRetryCountRef.current = 0;
    clearErrorRetry();
    const existing = getBarsEntry(symbol, timeframe);
    if (existing && existing.bars.length > 0) {
      applyStoreBars(existing.bars, { background: false, fitContent: true });
      setLoading(false);
      setError(null);
    }
    const unsub = subscribeBars(symbol, timeframe, () => {
      if (!chartActiveRef.current) return;
      const entry = getBarsEntry(symbol, timeframe);
      if (!entry) return;
      applyStoreBars(entry.bars, { background: true, fitContent: false });
    });
    return () => {
      clearErrorRetry();
      unsub();
    };
  }, [symbol, timeframe, onSeriesReset, applyStoreBars, clearErrorRetry]);

  // Network load when active and store is missing/stale.
  useEffect(() => {
    if (!chartActive) return;
    const entry = getBarsEntry(symbol, timeframe);
    const fresh = isBarsEntryFresh(entry, CHART_BARS_CLIENT_STALE_MS);
    if (fresh && entry && entry.bars.length > 0) {
      return;
    }
    const background = Boolean(entry && entry.bars.length > 0);
    const controller = new AbortController();
    void fetchBars(symbol, timeframe, background, controller.signal);
    return () => {
      barsRequestVersionRef.current += 1;
      controller.abort();
      clearErrorRetry();
    };
  }, [symbol, timeframe, fetchBars, chartActive, clearErrorRetry]);

  // Reconciliation poll -- paused while tab hidden.
  useEffect(() => {
    if (!chartActive) return;
    const sec = CHART_REFETCH_SEC[timeframe];
    if (!sec) return;
    const controller = new AbortController();
    const id = setInterval(() => {
      void fetchBars(symbol, timeframe, true, controller.signal);
    }, sec * 1000);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [symbol, timeframe, fetchBars, chartActive]);

  // Catch-up once when a hidden tab becomes active again.
  const wasActiveRef = useRef(chartActive);
  useEffect(() => {
    const was = wasActiveRef.current;
    wasActiveRef.current = chartActive;
    if (chartActive && !was) {
      void fetchBars(symbol, timeframe, true);
    }
  }, [chartActive, fetchBars, symbol, timeframe]);

  return { loading, error, usingMock, indicatorBars };
}
