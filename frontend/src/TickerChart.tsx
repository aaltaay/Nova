import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts';
import {
  DrawingManager,
  TrendLine,
  HorizontalLine,
  VerticalLine,
  CrossLine,
  type Anchor,
  type IDrawing,
} from 'lightweight-charts-drawing';
import {
  API_BASE_URL,
  CHART_DEFAULT_TIMEFRAME,
  CHART_HEIGHT_PANEL,
  CHART_HEIGHT_PAGE,
  CHART_HEIGHT_GRID,
  CHART_MOCK_BAR_COUNT,
  CHART_MOCK_BASE_PRICE,
  CHART_BARS_FETCH_TIMEOUT_MS,
  CHART_DEFAULT_INDICATORS,
  CHART_OSCILLATOR_IDS,
  CHART_REFETCH_SEC,
  type ChartIndicatorId,
  type ChartOscillatorId,
} from './constants';
import { TickerChartControls } from './components/TickerChartControls';
import { TickerChartErrorBoundary } from './components/TickerChartErrorBoundary';
import { TickerChartOverlays } from './components/TickerChartOverlays';
import { TickerChartOscillatorPanes } from './components/TickerChartOscillatorPanes';
import { useMaximizedChartPortal } from './hooks/useMaximizedChartPortal';
import {
  rawBarsToIndicatorBars,
  toggleIndicator,
  type IndicatorBar,
} from './chartIndicators';
import {
  buildMockBars,
  isOutOfOrderTrade,
  isoToEtTime,
  tradeBucket,
  type RawBar,
} from './tickerChartData';

const API_URL = `${API_BASE_URL}/api`;
export interface ChartTradeUpdate {
  price: number;
  timestamp: string | null;
}

// Single-click drawing tools (1 anchor each). TrendLine needs 2 anchors and is
// handled separately below. Style matches the chart's own crosshair color.
const DRAWING_STYLE = { lineColor: '#3b82f6', lineWidth: 1 };
const SINGLE_ANCHOR_TOOLS: Record<string, new (id: string, anchors: Anchor[], style: typeof DRAWING_STYLE) => IDrawing> = {
  HorizontalLine,
  VerticalLine,
  CrossLine,
};

interface TickerChartProps {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
  variant?: 'panel' | 'page' | 'grid';
  fixedTimeframe?: string;
  title?: string;
  subtitle?: string;
}

export function TickerChart(props: TickerChartProps) {
  return (
    <TickerChartErrorBoundary key={props.symbol}>
      <TickerChartInner {...props} />
    </TickerChartErrorBoundary>
  );
}

function TickerChartInner({
  symbol,
  lastTrade,
  variant = 'panel',
  fixedTimeframe,
  title,
  subtitle,
}: TickerChartProps) {
  const chartHeight =
    variant === 'grid' ? CHART_HEIGHT_GRID
    : variant === 'page' ? CHART_HEIGHT_PAGE
    : CHART_HEIGHT_PANEL;
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const managerRef = useRef<DrawingManager | null>(null);

  const [timeframe, setTimeframe] = useState(fixedTimeframe ?? CHART_DEFAULT_TIMEFRAME);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usingMock, setUsingMock] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [maximized, setMaximized] = useState(false);
  const [enabledIndicators, setEnabledIndicators] = useState<ChartIndicatorId[]>(
    () => [...CHART_DEFAULT_INDICATORS],
  );
  const [indicatorBars, setIndicatorBars] = useState<IndicatorBar[]>([]);
  const [chartApi, setChartApi] = useState<IChartApi | null>(null);
  const oscillatorEnabled = enabledIndicators.filter((id): id is ChartOscillatorId =>
    (CHART_OSCILLATOR_IDS as readonly ChartOscillatorId[]).includes(id as ChartOscillatorId),
  );
  const fillParentHeight = variant === 'grid' || maximized;
  const { slotRef, host } = useMaximizedChartPortal(maximized);
  const fillParentHeightRef = useRef(fillParentHeight);
  const chartHeightRef = useRef(chartHeight);
  fillParentHeightRef.current = fillParentHeight;
  chartHeightRef.current = chartHeight;

  const lastCandleRef = useRef<CandlestickData<Time> | null>(null);
  const prevTradeTsRef = useRef<string | null>(null);
  const barsRequestVersionRef = useRef(0);
  const activeToolRef = useRef<string | null>(null);
  const pendingAnchorRef = useRef<Anchor | null>(null);
  const lockTimeframe = !!fixedTimeframe;

  useEffect(() => {
    if (fixedTimeframe) setTimeframe(fixedTimeframe);
  }, [fixedTimeframe]);

  const handleChartClick = useCallback((param: MouseEventParams<Time>) => {
    const tool = activeToolRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    const manager = managerRef.current;
    if (!tool || !manager || !chart || !series || !param.point) return;

    const time = chart.timeScale().coordinateToTime(param.point.x);
    const price = series.coordinateToPrice(param.point.y);
    if (time === null || price === null) return;
    const anchor: Anchor = { time, price };

    if (tool === 'TrendLine') {
      const pending = pendingAnchorRef.current;
      if (!pending) {
        pendingAnchorRef.current = anchor;
        return;
      }
      manager.addDrawing(new TrendLine(`trendline-${Date.now()}`, [pending, anchor], DRAWING_STYLE));
      pendingAnchorRef.current = null;
      return;
    }

    const DrawingClass = SINGLE_ANCHOR_TOOLS[tool];
    if (DrawingClass) {
      manager.addDrawing(new DrawingClass(`${tool.toLowerCase()}-${Date.now()}`, [anchor], DRAWING_STYLE));
    }
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: { background: { color: '#161921' }, textColor: '#8b92a5' },
      grid: { vertLines: { color: '#262a36' }, horzLines: { color: '#262a36' } },
      crosshair: {
        vertLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
        horzLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
      },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#262a36' },
      rightPriceScale: { borderColor: '#262a36' },
      width: container.clientWidth,
      height: fillParentHeight
        ? Math.max(container.clientHeight || chartHeight, chartHeight)
        : chartHeight,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', downColor: '#ef4444',
      borderUpColor: '#10b981', borderDownColor: '#ef4444',
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });

    const volSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const manager = new DrawingManager();
    manager.attach(chart, candleSeries, container);
    chart.subscribeClick(handleChartClick);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volSeriesRef.current = volSeries;
    managerRef.current = manager;
    setChartApi(chart);

    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return;
      const ch = chartHeightRef.current;
      const h = fillParentHeightRef.current
        ? Math.max(containerRef.current.clientHeight || ch, ch)
        : ch;
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: h,
      });
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.unsubscribeClick(handleChartClick);
      manager.detach();
      chart.remove();
      setChartApi(null);
      chartRef.current = null;
      candleSeriesRef.current = null;
      volSeriesRef.current = null;
      managerRef.current = null;
    };
  }, [handleChartClick]);

  useEffect(() => {
    activeToolRef.current = activeTool;
    pendingAnchorRef.current = null;
    managerRef.current?.setActiveTool(activeTool);
    if (containerRef.current) {
      containerRef.current.style.cursor = activeTool ? 'crosshair' : 'default';
    }
  }, [activeTool]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (activeToolRef.current) {
        setActiveTool(null);
        return;
      }
      if (maximized) setMaximized(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [maximized]);

  useEffect(() => {
    const manager = managerRef.current;
    if (!manager) return;
    const unsub = manager.on('drawing:added', () => {
      setActiveTool(null);
    });
    return unsub;
  }, [chartApi]);

  // Reparenting the portal host changes size; ResizeObserver usually catches it,
  // but apply once after maximize toggle so the canvas never stays panel-sized.
  useEffect(() => {
    const container = containerRef.current;
    const chart = chartRef.current;
    if (!container || !chart) return;
    const ch = chartHeightRef.current;
    const h = fillParentHeightRef.current
      ? Math.max(container.clientHeight || ch, ch)
      : ch;
    chart.applyOptions({ width: container.clientWidth, height: h });
  }, [maximized, fillParentHeight, chartHeight]);

  const lastTradeRef = useRef<ChartTradeUpdate | null | undefined>(lastTrade);
  useEffect(() => {
    lastTradeRef.current = lastTrade;
  }, [lastTrade]);

  // Merges a live trade price into the in-progress candle for `tf`. Shared by
  // the trade-update effect below and by fetchBars' background refresh, so a
  // 10s Alpaca bar poll can't silently erase the latest live tick and make
  // the last candle jump backward (see PROBLEM_LOG 2026-07-14, "1Min chart
  // looks wrong / not live tick-by-tick").
  const applyLiveTrade = useCallback((trade: ChartTradeUpdate, tf: string) => {
    if (!trade.price || !trade.timestamp || !candleSeriesRef.current) return;
    const daily = tf === '1Day' || tf === '1Week' || tf === '1Month';
    if (daily) return;

    const bucket = tradeBucket(trade.timestamp, tf);
    if (bucket === null) return;
    const prev = lastCandleRef.current;
    if (isOutOfOrderTrade(prev, bucket)) return;
    const price = trade.price;

    if (prev && prev.time === bucket) {
      const updated: CandlestickData<Time> = {
        time: bucket,
        open: prev.open,
        high: Math.max(prev.high, price),
        low: Math.min(prev.low, price),
        close: price,
      };
      candleSeriesRef.current.update(updated);
      lastCandleRef.current = updated;
    } else {
      const newCandle: CandlestickData<Time> = {
        time: bucket, open: price, high: price, low: price, close: price,
      };
      candleSeriesRef.current.update(newCandle);
      lastCandleRef.current = newCandle;
    }
  }, []);

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
      if (requestVersion !== barsRequestVersionRef.current) return;
      let bars = data.bars ?? [];
      let mock = false;
      if (bars.length === 0) {
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
      // A background refresh replaces the whole series with Alpaca's version of
      // the in-progress bar, which can lag the live tick we already merged in.
      // Re-apply the last known live trade immediately so the candle doesn't
      // visibly snap backward on every poll.
      if (background) {
        setError(null);
        const liveTrade = lastTradeRef.current;
        if (liveTrade?.price && liveTrade.timestamp) applyLiveTrade(liveTrade, tf);
      }
    } catch (err) {
      if (requestVersion === barsRequestVersionRef.current && !background) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setError('Chart bars timed out — IBKR historical may be busy. Try again.');
        } else {
          setError(err instanceof Error ? err.message : 'Failed to load chart');
        }
      }
    } finally {
      window.clearTimeout(timeoutId);
      if (requestVersion === barsRequestVersionRef.current && !background) {
        setLoading(false);
      }
    }
  }, [applyLiveTrade]);

  useEffect(() => {
    prevTradeTsRef.current = null;
    lastCandleRef.current = null;
    void fetchBars(symbol, timeframe, false);
    return () => {
      barsRequestVersionRef.current += 1;
    };
  }, [symbol, timeframe, fetchBars]);

  useEffect(() => {
    const sec = CHART_REFETCH_SEC[timeframe];
    if (!sec) return;
    const id = setInterval(() => fetchBars(symbol, timeframe, true), sec * 1000);
    return () => clearInterval(id);
  }, [symbol, timeframe, fetchBars]);

  useEffect(() => {
    if (!lastTrade?.price || !lastTrade.timestamp) return;
    if (lastTrade.timestamp === prevTradeTsRef.current) return;
    prevTradeTsRef.current = lastTrade.timestamp;
    applyLiveTrade(lastTrade, timeframe);
  }, [lastTrade, timeframe, applyLiveTrade]);

  function handleToolClick(toolId: string) {
    setActiveTool(prev => (prev === toolId ? null : toolId));
  }

  function handleClearAll() {
    managerRef.current?.clearAll();
    setActiveTool(null);
  }

  function handleMaximize() {
    setMaximized(m => !m);
  }

  function handleIndicatorToggle(id: ChartIndicatorId) {
    setEnabledIndicators(prev => toggleIndicator(prev, id));
  }

  const card = (
    <div className={`chart-card${maximized ? ' chart-card--maximized' : ''}${variant === 'grid' ? ' chart-card--grid' : ''}`}>
      <TickerChartControls
        activeTool={activeTool}
        enabledIndicators={enabledIndicators}
        lockTimeframe={lockTimeframe}
        maximized={maximized}
        subtitle={subtitle}
        timeframe={timeframe}
        title={title}
        usingMock={usingMock}
        onClearAll={handleClearAll}
        onIndicatorToggle={handleIndicatorToggle}
        onMaximize={handleMaximize}
        onTimeframeChange={setTimeframe}
        onToolClick={handleToolClick}
      />

      <div className="chart-body" ref={containerRef}>
        {loading && <div className="chart-overlay">Loading…</div>}
        {!loading && error && <div className="chart-overlay chart-overlay--error">{error}</div>}
      </div>
      <TickerChartOverlays
        chart={chartApi}
        bars={indicatorBars}
        enabled={enabledIndicators}
      />
      {oscillatorEnabled.length > 0 && (
        <TickerChartOscillatorPanes
          parentChart={chartApi}
          bars={indicatorBars}
          enabled={oscillatorEnabled}
        />
      )}
    </div>
  );

  return (
    <div
      ref={slotRef}
      className={`chart-portal-slot${maximized ? ' chart-portal-slot--maximized' : ''}`}
      style={maximized ? { minHeight: chartHeight } : undefined}
    >
      {createPortal(card, host)}
    </div>
  );
}
