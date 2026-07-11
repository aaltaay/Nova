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
  type UTCTimestamp,
} from 'lightweight-charts';
import { DrawingManager } from 'lightweight-charts-drawing';
import {
  API_BASE_URL,
  CHART_TIMEFRAMES,
  CHART_DEFAULT_TIMEFRAME,
  CHART_CARD_TITLE,
  CHART_HEIGHT_PANEL,
  CHART_HEIGHT_PAGE,
  CHART_HEIGHT_GRID,
  CHART_MOCK_BAR_COUNT,
  CHART_MOCK_BASE_PRICE,
  CHART_MOCK_DATA_LABEL,
} from './constants';

const API_URL = `${API_BASE_URL}/api`;

interface RawBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

/** Trade data passed from the parent WebSocket stream. */
export interface ChartTradeUpdate {
  price: number;
  timestamp: string | null;
}

// ── Timezone helpers ─────────────────────────────────────────────────────────

function etOffsetMs(d: Date): number {
  const utcStr = d.toLocaleString('en-US', { timeZone: 'UTC' });
  const etStr  = d.toLocaleString('en-US', { timeZone: 'America/New_York' });
  return new Date(etStr).getTime() - new Date(utcStr).getTime();
}

function isoToEtTime(iso: string, isDailyOrAbove: boolean): Time {
  if (isDailyOrAbove) return iso.slice(0, 10) as Time;
  const d = new Date(iso);
  return Math.floor((d.getTime() + etOffsetMs(d)) / 1000) as UTCTimestamp;
}

function tfSeconds(tf: string): number {
  const m = tf.match(/^(\d+)(Min|Hour)$/);
  if (!m) return 60;
  return m[2] === 'Hour' ? +m[1] * 3600 : +m[1] * 60;
}

/** Synthetic OHLC when the API returns no bars — keeps drawing tools usable. */
function buildMockBars(count: number, basePrice: number): RawBar[] {
  const now = Date.now();
  const stepMs = 5 * 60 * 1000;
  const bars: RawBar[] = [];
  let price = basePrice;
  for (let i = count; i >= 1; i--) {
    const open = price;
    const drift = (Math.sin(i / 3) + Math.cos(i / 5)) * 0.08;
    const close = Math.max(0.5, open + drift);
    const high = Math.max(open, close) + 0.05;
    const low = Math.min(open, close) - 0.05;
    bars.push({
      t: new Date(now - i * stepMs).toISOString(),
      o: +open.toFixed(2),
      h: +high.toFixed(2),
      l: +low.toFixed(2),
      c: +close.toFixed(2),
      v: 10_000 + (i % 7) * 1_500,
    });
    price = close;
  }
  return bars;
}

const REFETCH_SEC: Record<string, number> = {
  '1Min': 10, '5Min': 15, '15Min': 30, '30Min': 30,
  '1Hour': 60, '4Hour': 120,
};

// ── Drawing tool definitions ─────────────────────────────────────────────────

interface DrawTool {
  id: string;
  label: string;
  icon: string;
}

const DRAW_TOOLS: DrawTool[] = [
  { id: 'TrendLine',      label: 'Trend Line',      icon: '╱' },
  { id: 'HorizontalLine', label: 'Horizontal Line',  icon: '─' },
  { id: 'VerticalLine',   label: 'Vertical Line',    icon: '│' },
  { id: 'CrossLine',      label: 'Crosshair',        icon: '┼' },
];

// ── Component ────────────────────────────────────────────────────────────────

export function TickerChart({
  symbol,
  lastTrade,
  variant = 'panel',
  fixedTimeframe,
  title,
  subtitle,
}: {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
  /** `page` = tall single chart; `panel` = side panel; `grid` = 2×2 cell. */
  variant?: 'panel' | 'page' | 'grid';
  /** Lock to one timeframe (hides timeframe tabs). */
  fixedTimeframe?: string;
  /** Override card title (defaults to CHART_CARD_TITLE). */
  title?: string;
  /** Optional note under the title (e.g. temp 15m stand-in). */
  subtitle?: string;
}) {
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

  const lastCandleRef = useRef<CandlestickData<Time> | null>(null);
  const prevTradeTsRef = useRef<string | null>(null);
  const lockTimeframe = !!fixedTimeframe;

  useEffect(() => {
    if (fixedTimeframe) setTimeframe(fixedTimeframe);
  }, [fixedTimeframe]);

  // ── Create / destroy chart + drawing manager ──────────────────────────
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
      height: maximized ? container.clientHeight : chartHeight,
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
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: maximized ? containerRef.current.clientHeight : chartHeight,
        });
      }
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
  }, [maximized, chartHeight]);

  // ── Sync active tool with drawing manager ─────────────────────────────
  useEffect(() => {
    managerRef.current?.setActiveTool(activeTool);
  }, [activeTool]);

  // ── Listen for drawing completion to auto-deselect tool ───────────────
  useEffect(() => {
    const manager = managerRef.current;
    if (!manager) return;
    const unsub = manager.on('drawing:added', () => {
      setActiveTool(null);
    });
    return unsub;
  }, [maximized]); // re-subscribe when manager is recreated

  // ── Fetch bars from REST ────────────────────────────────────────────────
  const fetchBars = useCallback(async (sym: string, tf: string, background = false) => {
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
      if (!background) setError(err instanceof Error ? err.message : 'Failed to load chart');
    } finally {
      if (!background) setLoading(false);
    }
  }, []);

  useEffect(() => { fetchBars(symbol, timeframe, false); }, [symbol, timeframe, fetchBars]);

  useEffect(() => {
    const sec = REFETCH_SEC[timeframe];
    if (!sec) return;
    const id = setInterval(() => fetchBars(symbol, timeframe, true), sec * 1000);
    return () => clearInterval(id);
  }, [symbol, timeframe, fetchBars]);

  // ── Real-time candle update from trade stream ──────────────────────────
  useEffect(() => {
    if (!lastTrade?.price || !lastTrade.timestamp) return;
    if (lastTrade.timestamp === prevTradeTsRef.current) return;
    prevTradeTsRef.current = lastTrade.timestamp;
    if (!candleSeriesRef.current) return;
    const daily = timeframe === '1Day' || timeframe === '1Week' || timeframe === '1Month';
    if (daily) return;

    const d = new Date(lastTrade.timestamp);
    const etSec = Math.floor((d.getTime() + etOffsetMs(d)) / 1000);
    const bucket = (Math.floor(etSec / tfSeconds(timeframe)) * tfSeconds(timeframe)) as UTCTimestamp as Time;
    const prev = lastCandleRef.current;
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

  // ── Tool handlers ──────────────────────────────────────────────────────

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

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className={`chart-card${maximized ? ' chart-card--maximized' : ''}${variant === 'grid' ? ' chart-card--grid' : ''}`}>
      <div className="chart-header">
        <div className="chart-title-block">
          <span className="chart-title">{title ?? CHART_CARD_TITLE}</span>
          {subtitle && <span className="chart-subtitle" title={subtitle}>{subtitle}</span>}
        </div>
        {usingMock && (
          <span className="chart-mock-badge" title={CHART_MOCK_DATA_LABEL}>{CHART_MOCK_DATA_LABEL}</span>
        )}
        {!lockTimeframe && (
          <div className="chart-tabs" role="group" aria-label="Timeframe">
            {CHART_TIMEFRAMES.map(tf => (
              <button
                key={tf.id}
                className={`chart-tab${timeframe === tf.id ? ' chart-tab--active' : ''}`}
                onClick={() => setTimeframe(tf.id)}
                aria-pressed={timeframe === tf.id}
              >
                {tf.label}
              </button>
            ))}
          </div>
        )}
        {lockTimeframe && (
          <span className="chart-tf-badge" aria-label={`Timeframe ${timeframe}`}>{timeframe}</span>
        )}
      </div>

      {/* Drawing toolbar */}
      <div className="chart-toolbar">
        {DRAW_TOOLS.map(tool => (
          <button
            key={tool.id}
            className={`chart-tool-btn${activeTool === tool.id ? ' chart-tool-btn--active' : ''}`}
            onClick={() => handleToolClick(tool.id)}
            title={tool.label}
          >
            <span className="chart-tool-icon">{tool.icon}</span>
          </button>
        ))}
        <button
          className="chart-tool-btn chart-tool-btn--danger"
          onClick={handleClearAll}
          title="Clear all drawings"
        >
          <span className="chart-tool-icon">✕</span>
        </button>
        <div className="chart-toolbar-spacer" />
        <button
          className={`chart-tool-btn${maximized ? ' chart-tool-btn--active' : ''}`}
          onClick={handleMaximize}
          title={maximized ? 'Restore' : 'Maximize'}
        >
          <span className="chart-tool-icon">{maximized ? '⊙' : '⛶'}</span>
        </button>
      </div>

      <div className="chart-body" ref={containerRef}>
        {loading && <div className="chart-overlay">Loading…</div>}
        {!loading && error && <div className="chart-overlay chart-overlay--error">{error}</div>}
      </div>
    </div>
  );
}
