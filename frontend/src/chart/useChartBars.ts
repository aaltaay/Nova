/** ADR 005 / 012 -- store-first bar loading; fills arrive as bars_patch.
 * A pane with no periodic refetch (see CHART_REFETCH_SEC) still self-heals if
 * the one-shot fetch lands empty+filling and the bars_patch push is missed
 * (see the stuck-retry effect below / chartBarsStuckRetry.ts). */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  CandlestickData,
  IChartApi,
  ISeriesApi,
  Time,
} from 'lightweight-charts';
import {
  CHART_BARS_CLIENT_STALE_MS,
  CHART_BARS_STUCK_RETRY_MAX_MS,
  CHART_BARS_STUCK_RETRY_MIN_MS,
  CHART_MOCK_BAR_COUNT,
  CHART_MOCK_BASE_PRICE,
  CHART_REFETCH_SEC,
  CHART_TIMEFRAME_BAR_LIMITS,
} from '../constants';
import { isStuckLoadingBars, startStuckBarsRetries } from './chartBarsStuckRetry';
import {
  rawBarsToIndicatorBars,
  type IndicatorBar,
} from '../chartIndicators';
import {
  buildMockBars,
  canIncrementalBarsUpdate,
  rawBarsToSeries,
  timeScaleRangeForSeries,
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
  chartActive?: boolean;
}

function applyTimeScale(
  chartRef: UseChartBarsOptions['chartRef'],
  timeframe: string,
  candleCount: number,
): void {
  const chart = chartRef.current;
  if (!chart || candleCount <= 0) return;
  const range = timeScaleRangeForSeries(timeframe, candleCount);
  if (range) chart.timeScale().setVisibleLogicalRange(range);
  else chart.timeScale().fitContent();
}

function paintFull(
  candles: CandlestickData<Time>[],
  volumes: ReturnType<typeof rawBarsToSeries>['volumes'],
  candleSeriesRef: UseChartBarsOptions['candleSeriesRef'],
  volSeriesRef: UseChartBarsOptions['volSeriesRef'],
  chartRef: UseChartBarsOptions['chartRef'],
  timeframe: string,
): void {
  candleSeriesRef.current?.setData(candles);
  volSeriesRef.current?.setData(volumes);
  applyTimeScale(chartRef, timeframe, candles.length);
  requestAnimationFrame(() => {
    applyTimeScale(chartRef, timeframe, candles.length);
  });
}

function paintBars(
  bars: RawBar[],
  tf: string,
  candleSeriesRef: UseChartBarsOptions['candleSeriesRef'],
  volSeriesRef: UseChartBarsOptions['volSeriesRef'],
  lastCandleRef: UseChartBarsOptions['lastCandleRef'],
  chartRef: UseChartBarsOptions['chartRef'],
  prevBars: RawBar[] | null,
): IndicatorBar[] {
  const { candles, volumes } = rawBarsToSeries(bars, tf);
  const canIncremental =
    prevBars != null
    && canIncrementalBarsUpdate(prevBars, bars)
    && candleSeriesRef.current
    && volSeriesRef.current
    && candles.length > 0;

  if (canIncremental) {
    const tip = candles[candles.length - 1];
    const tipVol = volumes[volumes.length - 1];
    try {
      candleSeriesRef.current!.update(tip);
      volSeriesRef.current!.update(tipVol);
    } catch {
      paintFull(candles, volumes, candleSeriesRef, volSeriesRef, chartRef, tf);
    }
  } else {
    paintFull(candles, volumes, candleSeriesRef, volSeriesRef, chartRef, tf);
  }
  lastCandleRef.current = candles.length > 0 ? candles[candles.length - 1] : null;
  return rawBarsToIndicatorBars(bars, tf);
}

function coverageFromEntry(symbol: string, timeframe: string): {
  filling: boolean;
  asOf: string | null;
} {
  const cov = getBarsEntry(symbol, timeframe)?.coverage;
  return { filling: Boolean(cov?.filling), asOf: cov?.asOf ?? null };
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
  const [filling, setFilling] = useState(false);
  const [coverageAsOf, setCoverageAsOf] = useState<string | null>(null);
  const [indicatorBars, setIndicatorBars] = useState<IndicatorBar[]>([]);

  const barsRequestVersionRef = useRef(0);
  const lastTradeRef = useRef<ChartTradeUpdate | null | undefined>(lastTrade);
  const paintedBarsRef = useRef<RawBar[] | null>(null);
  const chartActiveRef = useRef(chartActive);

  useEffect(() => {
    lastTradeRef.current = lastTrade;
  }, [lastTrade]);

  useEffect(() => {
    chartActiveRef.current = chartActive;
  }, [chartActive]);

  const applyCoverage = useCallback((sym: string, tf: string) => {
    const next = coverageFromEntry(sym, tf);
    setFilling(next.filling);
    setCoverageAsOf(next.asOf);
  }, []);

  const applyStoreBars = useCallback((
    bars: RawBar[],
    opts: { background: boolean; filling?: boolean },
  ) => {
    let next = bars;
    let mock = false;
    if (next.length === 0) {
      if (opts.filling) {
        setUsingMock(false);
        setError(null);
        return;
      }
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
    );
    paintedBarsRef.current = next;
    setIndicatorBars(indicators);
    setError(null);
    const liveTrade = lastTradeRef.current;
    if (liveTrade?.price && liveTrade.timestamp) applyLiveTrade(liveTrade, timeframe);
  }, [
    applyLiveTrade,
    candleSeriesRef,
    chartRef,
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
      const cov = coverageFromEntry(sym, tf);
      applyCoverage(sym, tf);
      applyStoreBars(bars, {
        background,
        filling: cov.filling,
      });
    } catch (err) {
      if (!isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current)) return;
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (!background) {
        setError(err instanceof Error ? err.message : 'Failed to load chart');
      }
    } finally {
      if (isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current) && !background) {
        setLoading(false);
      }
    }
  }, [applyCoverage, applyStoreBars]);

  useEffect(() => {
    onSeriesReset();
    paintedBarsRef.current = null;
    setIndicatorBars([]);
    setFilling(false);
    setCoverageAsOf(null);
    const existing = getBarsEntry(symbol, timeframe);
    if (existing && existing.bars.length > 0) {
      applyCoverage(symbol, timeframe);
      applyStoreBars(existing.bars, {
        background: false,
        filling: Boolean(existing.coverage?.filling),
      });
      setLoading(false);
      setError(null);
    }
    const unsub = subscribeBars(symbol, timeframe, () => {
      if (!chartActiveRef.current) return;
      const entry = getBarsEntry(symbol, timeframe);
      if (!entry) return;
      applyCoverage(symbol, timeframe);
      applyStoreBars(entry.bars, {
        background: true,
        filling: Boolean(entry.coverage?.filling),
      });
    });
    return unsub;
  }, [symbol, timeframe, onSeriesReset, applyStoreBars, applyCoverage]);

  useEffect(() => {
    if (!chartActive) return;
    const entry = getBarsEntry(symbol, timeframe);
    const fresh = isBarsEntryFresh(entry, CHART_BARS_CLIENT_STALE_MS);
    if (fresh && entry && entry.bars.length > 0 && !entry.coverage?.filling) {
      return;
    }
    const background = Boolean(entry && entry.bars.length > 0);
    const controller = new AbortController();
    void fetchBars(symbol, timeframe, background, controller.signal);
    return () => {
      barsRequestVersionRef.current += 1;
      controller.abort();
    };
  }, [symbol, timeframe, fetchBars, chartActive]);

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

  const wasActiveRef = useRef(chartActive);
  useEffect(() => {
    const was = wasActiveRef.current;
    wasActiveRef.current = chartActive;
    if (chartActive && !was) {
      void fetchBars(symbol, timeframe, true);
    }
  }, [chartActive, fetchBars, symbol, timeframe]);

  useEffect(() => {
    const stuck = isStuckLoadingBars({
      filling,
      hasBars: indicatorBars.length > 0,
      chartActive,
    });
    if (!stuck) return;
    const controller = new AbortController();
    const stop = startStuckBarsRetries(
      () => {
        void fetchBars(symbol, timeframe, true, controller.signal);
      },
      CHART_BARS_STUCK_RETRY_MIN_MS,
      CHART_BARS_STUCK_RETRY_MAX_MS,
    );
    return () => {
      stop();
      controller.abort();
    };
  }, [symbol, timeframe, chartActive, filling, indicatorBars.length, fetchBars]);

  return { loading, error, usingMock, indicatorBars, filling, coverageAsOf };
}
