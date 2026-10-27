import { useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
import { useChartInstance } from '../../src/chart/useChartInstance';

/**
 * #459: Nova's own chart instance (useChartInstance) at a chosen width, over
 * 1-minute sample candles that cross a year boundary, so the axis carries
 * year, day and clock labels. `?w=` sets the pane width in CSS pixels.
 */
const width = Number(new URLSearchParams(location.search).get('w') ?? 800);

/** ET wall clock encoded as UTC, as tickerChartData.isoToEtTime does. */
function sampleBars() {
  const days = [
    { day: Date.UTC(2025, 11, 30), from: 9 * 60 + 30 },
    { day: Date.UTC(2025, 11, 31), from: 9 * 60 + 30 },
    { day: Date.UTC(2026, 0, 2), from: 9 * 60 + 30 },
  ];
  const bars: { time: UTCTimestamp; open: number; high: number; low: number; close: number; value: number }[] = [];
  let price = 4;
  for (const { day, from } of days) {
    for (let minute = from; minute < 16 * 60; minute++) {
      const open = price;
      price = Math.max(1, price + Math.sin(bars.length / 7) * 0.05);
      bars.push({
        time: ((day + minute * 60_000) / 1000) as UTCTimestamp,
        open, close: price, high: Math.max(open, price) + 0.03, low: Math.min(open, price) - 0.03,
        value: 1000 + (bars.length % 50) * 40,
      });
    }
  }
  return bars;
}

declare global {
  interface Window { __chart?: IChartApi; __barCount?: number }
}

function Chart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const chart = useChartInstance({
    containerRef, chartRef, candleSeriesRef, volSeriesRef,
    chartHeight: 300, fillParentHeight: false, maximized: false,
  });
  useEffect(() => {
    if (!chart) return;
    const bars = sampleBars();
    candleSeriesRef.current?.setData(bars);
    volSeriesRef.current?.setData(bars.map(({ time, value }) => ({ time, value })));
    window.__chart = chart;
    window.__barCount = bars.length;
  }, [chart]);
  return <div ref={containerRef} data-testid="chart" style={{ width, height: 300 }} />;
}

createRoot(document.getElementById('root')!).render(<Chart />);
