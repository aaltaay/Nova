import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
} from 'lightweight-charts';
import { DrawingManager } from 'lightweight-charts-drawing';
import {
  API_BASE_URL,
  CHART_DEFAULT_TIMEFRAME,
  CHART_HEIGHT_PANEL,
  CHART_HEIGHT_PAGE,
  CHART_HEIGHT_GRID,
  CHART_MOCK_BAR_COUNT,
  CHART_MOCK_BASE_PRICE,
  CHART_REFETCH_SEC,
} from './constants';
import { TickerChartControls } from './components/TickerChartControls';
import { TickerChartErrorBoundary } from './components/TickerChartErrorBoundary';
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
  const fillParentHeight = variant === 'grid' || maximized;

  const lastCandleRef = useRef<CandlestickData<Time> | null>(null);
  const prevTradeTsRef = useRef<string | null>(null);
  const barsRequestVersionRef = useRef(0);
  const lockTimeframe = !!fixedTimeframe;

  useEffect(() => {
    if (fixedTimeframe) setTimeframe(fixedTimeframe);
  }, [fixedTimeframe]);

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

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volSeriesRef.current = volSeries;
    managerRef.current = manager;

    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return;
      const h = fillParentHeight
        ? Math.max(containerRef.current.clientHeight || chartHeight, chartHeight)
        : chartHeight;
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: h,
      });
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      manager.detach();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volSeriesRef.current = null;
      managerRef.current = null;
    };
  }, [maximized, chartHeight, fillParentHeight]);

  useEffect(() => {
    managerRef.current?.setActiveTool(activeTool);
  }, [activeTool]);

  useEffect(() => {
    const manager = managerRef.current;
    if (!manager) return;
    const unsub = manager.on('drawing:added', () => {
      setActiveTool(null);
    });
    return unsub;
  }, [maximized]);

  const fetchBars = useCallback(async (sym: string, tf: string, background = false) => {
    const requestVersion = ++barsRequestVersionRef.current;
    if (!background) {
      setLoading(true);
      setError(null);
    }
    try {
      const res = await fetch(`${API_URL}/ticker/${sym}/bars?timeframe=${tf}`);
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
      if (!background && candles.length > 0) chartRef.current?.timeScale().fitContent();
      if (background) setError(null);
    } catch (err) {
      if (requestVersion === barsRequestVersionRef.current && !background) {
        setError(err instanceof Error ? err.message : 'Failed to load chart');
      }
    } finally {
      if (requestVersion === barsRequestVersionRef.current && !background) {
        setLoading(false);
      }
    }
  }, []);

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
    if (!candleSeriesRef.current) return;
    const daily = timeframe === '1Day' || timeframe === '1Week' || timeframe === '1Month';
    if (daily) return;

    const bucket = tradeBucket(lastTrade.timestamp, timeframe);
    if (bucket === null) return;
    const prev = lastCandleRef.current;
    if (isOutOfOrderTrade(prev, bucket)) return;
    const price = lastTrade.price;

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
  }, [lastTrade, timeframe]);

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

  return (
    <div className={`chart-card${maximized ? ' chart-card--maximized' : ''}${variant === 'grid' ? ' chart-card--grid' : ''}`}>
      <TickerChartControls
        activeTool={activeTool}
        lockTimeframe={lockTimeframe}
        maximized={maximized}
        subtitle={subtitle}
        timeframe={timeframe}
        title={title}
        usingMock={usingMock}
        onClearAll={handleClearAll}
        onMaximize={handleMaximize}
        onTimeframeChange={setTimeframe}
        onToolClick={handleToolClick}
      />

      <div className="chart-body" ref={containerRef}>
        {loading && <div className="chart-overlay">Loading…</div>}
        {!loading && error && <div className="chart-overlay chart-overlay--error">{error}</div>}
      </div>
    </div>
  );
}
