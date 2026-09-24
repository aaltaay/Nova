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
import { rawBarsToIndicatorBars, type IndicatorBar } from '../chartIndicators';
import {
  buildMockBars,
  type RawBar,
} from '../tickerChartData';
import { useWorkspace } from '../workspace';
import { allowMockBarsFallback, chartEmptyText } from './chartBarsPolicy';
import { useSimReplayTarget } from '../sim/useSimReplayTarget';
import { paintBars } from './chartBarsPaint';
import {
  snapshotChartViewport,
  type ChartViewportSnapshot,
} from './chartViewportPaint';
import {
  barsStoreKey,
  ensureBars,
  getBarsEntry,
  isBarsEntryFresh,
  subscribeBars,
} from './barsStore';
import { isCurrentBarsRequest } from './requestVersion';
import type { ChartTradeUpdate } from './types';
import { createRafCoalesce } from '../utils/rafCoalesce';
import { matchesSimClockScrub, SIM_CLOCK_SCRUB_EVENT } from '../sim/simClockEvents';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { invalidateReplayBars, subscribeReplayBarsRefresh } from './replayBarsRefresh';

interface UseChartBarsOptions {
  symbol: string;
  timeframe: string;
  chartRef: React.RefObject<IChartApi | null>;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  volSeriesRef: React.RefObject<ISeriesApi<'Histogram'> | null>;
  lastCandleRef: React.RefObject<CandlestickData<Time> | null>;
  lastTrade: ChartTradeUpdate | null | undefined;
  /** After a store paint: put the live tip (candle and volume) back on top. */
  restoreAfterStorePaint: (
    storeTipVolume: number | null,
    trade: ChartTradeUpdate | null | undefined,
    tf: string,
  ) => void;
  onSeriesReset: () => void;
  chartActive?: boolean;
}

function coverageFromEntry(symbol: string, timeframe: string): {
  filling: boolean;
  asOf: string | null;
  lastError: string | null;
  lastErrorTs: number | null;
} {
  const cov = getBarsEntry(symbol, timeframe)?.coverage;
  return {
    filling: Boolean(cov?.filling),
    asOf: cov?.asOf ?? null,
    lastError: cov?.lastError ?? null,
    lastErrorTs: cov?.lastErrorTs ?? null,
  };
}

export function useChartBars({
  symbol,
  timeframe,
  chartRef,
  candleSeriesRef,
  volSeriesRef,
  lastCandleRef,
  lastTrade,
  restoreAfterStorePaint,
  onSeriesReset,
  chartActive = true,
}: UseChartBarsOptions) {
  const { discoveryProvider } = useWorkspace();
  const sim = useIbkrStatus().mode === 'sim';
  const replay = useSimReplayTarget(symbol);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** The pane answered with no bars -- a stated absence, not an error (QA V9). */
  const [empty, setEmpty] = useState(false);
  const [usingMock, setUsingMock] = useState(false);
  const [filling, setFilling] = useState(false);
  const [coverageAsOf, setCoverageAsOf] = useState<string | null>(null);
  /** IBKR history did not answer this pane's last fill (coverage `last_error`, #555). */
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyErrorTs, setHistoryErrorTs] = useState<number | null>(null);
  const [indicatorBars, setIndicatorBars] = useState<IndicatorBar[]>([]);

  const barsRequestVersionRef = useRef(0);
  const lastTradeRef = useRef<ChartTradeUpdate | null | undefined>(lastTrade);
  const paintedBarsRef = useRef<RawBar[] | null>(null);
  /**
   * Survives a transient empty refresh, a Paper / Live / Sim switch and a
   * hidden Trader tab coming back, so the next paint restores the operator's
   * window instead of refitting. Cleared by a Sim seek or a new symbol /
   * timeframe, which SHOULD refit -- the time window genuinely changed.
   */
  const pendingViewportRef = useRef<ChartViewportSnapshot | null>(null);
  /** The pane (symbol + timeframe) the pending viewport belongs to. */
  const viewportPaneRef = useRef<string | null>(null);
  const paintEpochRef = useRef(0);
  const chartActiveRef = useRef(chartActive);

  /**
   * Hold the operator's window before the series is cleared: once it is, the
   * time scale reports nothing and the next paint would read as the first.
   * Consecutive clears keep the first capture.
   */
  const carryViewport = useCallback(() => {
    pendingViewportRef.current =
      snapshotChartViewport(chartRef.current, paintedBarsRef.current?.length ?? 0)
      ?? pendingViewportRef.current;
  }, [chartRef]);

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
    setHistoryError(next.lastError);
    setHistoryErrorTs(next.lastErrorTs);
  }, []);

  const applyStoreBars = useCallback((
    bars: RawBar[],
    opts: { background: boolean; filling?: boolean },
  ) => {
    let next = bars;
    let mock = false;
    if (next.length === 0) {
      if (opts.filling && !sim) {
        setUsingMock(false);
        setError(null);
        setEmpty(false);
        return;
      }
      if (sim || !allowMockBarsFallback(discoveryProvider)) {
        // Before the wipe: `paintedBarsRef = []` would make the next paint
        // look like the first one.
        carryViewport();
        setUsingMock(false);
        setIndicatorBars([]);
        candleSeriesRef.current?.setData([]);
        volSeriesRef.current?.setData([]);
        lastCandleRef.current = null;
        paintedBarsRef.current = [];
        setError(null);
        setEmpty(true);
        return;
      }
      next = buildMockBars(CHART_MOCK_BAR_COUNT, CHART_MOCK_BASE_PRICE);
      mock = true;
    }
    setUsingMock(mock);
    const painted = paintBars(
      next,
      timeframe,
      candleSeriesRef,
      volSeriesRef,
      lastCandleRef,
      chartRef,
      paintedBarsRef.current,
      paintEpochRef,
      pendingViewportRef.current,
    );
    pendingViewportRef.current = null;
    paintedBarsRef.current = next;
    setEmpty(false);
    if (sim) {
      setIndicatorBars(rawBarsToIndicatorBars(next, timeframe));
    } else if (!painted.skipIndicatorCommit) {
      setIndicatorBars(painted.indicators);
    }
    setError(null);
    restoreAfterStorePaint(next.at(-1)?.v ?? null, lastTradeRef.current, timeframe);
  }, [
    restoreAfterStorePaint,
    candleSeriesRef,
    carryViewport,
    chartRef,
    discoveryProvider,
    sim,
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
    // Same pane re-sourced (the desk's venue changed): keep the operator's
    // window. A new symbol or timeframe is a different chart and refits.
    const pane = barsStoreKey(symbol, timeframe);
    if (viewportPaneRef.current === pane) {
      carryViewport();
    } else {
      viewportPaneRef.current = pane;
      pendingViewportRef.current = null;
    }
    onSeriesReset();
    paintedBarsRef.current = null;
    setIndicatorBars([]);
    setEmpty(false);
    setFilling(false);
    setCoverageAsOf(null);
    setHistoryError(null);
    setHistoryErrorTs(null);
    const existing = getBarsEntry(symbol, timeframe);
    if (existing && existing.bars.length > 0 && Boolean(existing.coverage?.replay) === sim) {
      applyCoverage(symbol, timeframe);
      applyStoreBars(existing.bars, {
        background: false,
        filling: Boolean(existing.coverage?.filling),
      });
      setLoading(false);
      setError(null);
    }
    const applyFromStore = () => {
      if (!chartActiveRef.current) return;
      const entry = getBarsEntry(symbol, timeframe);
      if (!entry) return;
      applyCoverage(symbol, timeframe);
      applyStoreBars(entry.bars, {
        background: true,
        filling: Boolean(entry.coverage?.filling),
      });
    };
    const raf = createRafCoalesce(applyFromStore);
    const unsub = subscribeBars(symbol, timeframe, () => {
      raf.schedule();
    });
    return () => {
      raf.cancel();
      unsub();
    };
  }, [symbol, timeframe, onSeriesReset, applyStoreBars, applyCoverage, carryViewport, sim]);

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

  
  // Sim scrubber - drop cache and refetch so charts honor session clock jumps.
  // Also runs, with no event, when the venue changes or a hidden tab returns:
  // those re-source the same window, so the operator's zoom and pan carry over.
  useEffect(() => {
    if (!chartActive) return undefined;
    const onScrub = (event?: Event) => {
      if (event && (!sim || !matchesSimClockScrub(event, symbol))) return;
      barsRequestVersionRef.current += 1;
      if (event) pendingViewportRef.current = null;
      else carryViewport();
      onSeriesReset();
      paintedBarsRef.current = null;
      setIndicatorBars([]);
      candleSeriesRef.current?.setData([]);
      volSeriesRef.current?.setData([]);
      invalidateReplayBars(event, symbol, timeframe);
      void fetchBars(symbol, timeframe, false);
    };
    onScrub();
    window.addEventListener(SIM_CLOCK_SCRUB_EVENT, onScrub);
    return () => window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, onScrub);
  }, [
    symbol, timeframe, chartActive, fetchBars, sim, onSeriesReset, carryViewport,
    candleSeriesRef, volSeriesRef,
  ]);

useEffect(() => {
    if (!chartActive) return;
    const controller = new AbortController();
    const refresh = () => { void fetchBars(symbol, timeframe, true, controller.signal); };
    if (sim) {
      const stop = subscribeReplayBarsRefresh(symbol, timeframe, refresh);
      return () => { controller.abort(); stop(); };
    }
    const interval = (CHART_REFETCH_SEC[timeframe] ?? 0) * 1000;
    if (!interval) return;
    const id = setInterval(refresh, interval);
    return () => { controller.abort(); clearInterval(id); };
  }, [symbol, timeframe, fetchBars, chartActive, sim]);

  const wasActiveRef = useRef(chartActive);
  useEffect(() => {
    const was = wasActiveRef.current;
    wasActiveRef.current = chartActive;
    if (chartActive && !was) {
      const entry = getBarsEntry(symbol, timeframe);
      if (entry && entry.bars.length > 0) {
        applyCoverage(symbol, timeframe);
        applyStoreBars(entry.bars, {
          background: true,
          filling: Boolean(entry.coverage?.filling),
        });
      }
      void fetchBars(symbol, timeframe, true);
    }
  }, [chartActive, fetchBars, symbol, timeframe, applyCoverage, applyStoreBars]);

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

  const emptyText = empty ? chartEmptyText(sim, replay.target, discoveryProvider) : null;
  return {
    loading, error, emptyText, usingMock, indicatorBars, filling, coverageAsOf,
    historyError, historyErrorTs,
  };
}
