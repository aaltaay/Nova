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
  const incremental =
    prevBars != null
    && canIncrementalBarsUpdate(prevBars, bars)
    && candleSeriesRef.current
    && volSeriesRef.current;

  if (incremental) {
    const start = Math.max(0, candles.length - 2);
    for (let i = start; i < candles.length; i++) {
      candleSeriesRef.current!.update(candles[i]);
      volSeriesRef.current!.update(volumes[i]);
    }
  } else {
    candleSeriesRef.current?.setData(candles);
    volSeriesRef.current?.setData(volumes);
    if (fitContent && candles.length > 0) chartRef.current?.timeScale().fitContent();
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

  useEffect(() => {
    lastTradeRef.current = lastTrade;
  }, [lastTrade]);

  useEffect(() => {
    chartActiveRef.current = chartActive;
  }, [chartActive]);

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
    if (opts.background) {
      setError(null);
      const liveTrade = lastTradeRef.current;
      if (liveTrade?.price && liveTrade.timestamp) applyLiveTrade(liveTrade, timeframe);
    }
  }, [
    applyLiveTrade,
    candleSeriesRef,
    chartRef,
    discoveryProvider,
    lastCandleRef,
    timeframe,
    volSeriesRef,
  ]);

  const fetchBars = useCallback(async (sym: string, tf: string, background = false) => {
    const requestVersion = ++barsRequestVersionRef.current;
    if (!background) {
      setLoading(true);
      setError(null);
    }
    const controller = new AbortController();
    try {
      const bars = await ensureBars(sym, tf, controller.signal);
      if (!isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current)) return;
      applyStoreBars(bars, { background, fitContent: !background });
    } catch (err) {
      if (isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current) && !background) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setError('Chart bars timed out -- IBKR historical may be busy. Try again.');
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load chart');
        }
      }
    } finally {
      if (isCurrentBarsRequest(requestVersion, barsRequestVersionRef.current) && !background) {
        setLoading(false);
      }
    }
  }, [applyStoreBars]);

  // Instant paint from shared store; subscribe for batch/warm updates.
  useEffect(() => {
    onSeriesReset();
    paintedBarsRef.current = null;
    const existing = getBarsEntry(symbol, timeframe);
    if (existing && existing.bars.length > 0) {
      applyStoreBars(existing.bars, { background: false, fitContent: true });
      setLoading(false);
      setError(null);
    }
    return subscribeBars(symbol, timeframe, () => {
      if (!chartActiveRef.current) return;
      const entry = getBarsEntry(symbol, timeframe);
      if (!entry) return;
      applyStoreBars(entry.bars, { background: true, fitContent: false });
    });
  }, [symbol, timeframe, onSeriesReset, applyStoreBars]);

  // Network load when active and store is missing/stale.
  useEffect(() => {
    if (!chartActive) return;
    const entry = getBarsEntry(symbol, timeframe);
    const fresh = isBarsEntryFresh(entry, CHART_BARS_CLIENT_STALE_MS);
    if (fresh && entry && entry.bars.length > 0) {
      return;
    }
    const background = Boolean(entry && entry.bars.length > 0);
    void fetchBars(symbol, timeframe, background);
    return () => {
      barsRequestVersionRef.current += 1;
    };
  }, [symbol, timeframe, fetchBars, chartActive]);

  // Reconciliation poll -- paused while tab hidden.
  useEffect(() => {
    if (!chartActive) return;
    const sec = CHART_REFETCH_SEC[timeframe];
    if (!sec) return;
    const id = setInterval(() => {
      void fetchBars(symbol, timeframe, true);
    }, sec * 1000);
    return () => clearInterval(id);
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
