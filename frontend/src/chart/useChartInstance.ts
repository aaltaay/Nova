/** ADR 005 -- lightweight-charts instance lifecycle, series refs, and resize. */

import { useEffect, useRef, useState, type RefObject } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type TickMarkType,
  type Time,
} from 'lightweight-charts';
import { formatChartCrosshairTime, formatChartTickMark } from './chartTimeFormat';
import { CHART_CROSSHAIR_OPTIONS } from './chartInteractionConfig';
import { measureChartFillHeight } from './measureChartFillHeight';
import { isSubMinuteTimeframe } from '../tickerChartData';

export interface ChartSeriesRefs {
  chartRef: RefObject<IChartApi | null>;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  volSeriesRef: RefObject<ISeriesApi<'Histogram'> | null>;
}

interface UseChartInstanceOptions extends ChartSeriesRefs {
  containerRef: RefObject<HTMLDivElement | null>;
  chartHeight: number;
  fillParentHeight: boolean;
  maximized: boolean;
  /** Drives secondsVisible + second-aware axis labels for 10Sec panes. */
  timeframe?: string;
  /** When false, skip ResizeObserver apply (hidden Trader tab). */
  chartActive?: boolean;
  /** Remeasure fill height when RSI/MACD panes mount or unmount. */
  oscillatorPaneCount?: number;
  /** Grid maximize/restore -- sibling panes also remeasure when the layout flips. */
  layoutEpoch?: string | null;
}

export function useChartInstance({
  containerRef,
  chartRef,
  candleSeriesRef,
  volSeriesRef,
  chartHeight,
  fillParentHeight,
  maximized,
  timeframe = '1Min',
  chartActive = true,
  oscillatorPaneCount = 0,
  layoutEpoch = null,
}: UseChartInstanceOptions): IChartApi | null {
  const [chartApi, setChartApi] = useState<IChartApi | null>(null);

  const fillParentHeightRef = useRef(fillParentHeight);
  const chartHeightRef = useRef(chartHeight);
  const chartActiveRef = useRef(chartActive);
  const showSecondsRef = useRef(isSubMinuteTimeframe(timeframe));

  useEffect(() => {
    fillParentHeightRef.current = fillParentHeight;
    chartHeightRef.current = chartHeight;
    chartActiveRef.current = chartActive;
  }, [fillParentHeight, chartHeight, chartActive]);

  useEffect(() => {
    showSecondsRef.current = isSubMinuteTimeframe(timeframe);
    chartRef.current?.applyOptions({
      timeScale: { secondsVisible: showSecondsRef.current },
    });
  }, [timeframe, chartRef]);

  // Create/destroy once per container mount -- height/fill changes only applyOptions.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialHeight = fillParentHeightRef.current
      ? measureChartFillHeight(container, chartHeightRef.current)
      : chartHeightRef.current;

    const chart = createChart(container, {
      layout: { background: { color: '#161921' }, textColor: '#8b92a5' },
      grid: { vertLines: { color: '#262a36' }, horzLines: { color: '#262a36' } },
      crosshair: CHART_CROSSHAIR_OPTIONS,
      localization: {
        locale: 'en-US',
        timeFormatter: (t: Time) => formatChartCrosshairTime(t, showSecondsRef.current),
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: showSecondsRef.current,
        borderColor: '#262a36',
        // Incremental series.update of a new tip bar keeps zoom and only
        // walks the right edge. Full setData uses chartViewportPaint.
        shiftVisibleRangeOnNewBar: true,
        tickMarkFormatter: (t: Time, tickMarkType: TickMarkType, locale: string) =>
          formatChartTickMark(t, tickMarkType, locale, showSecondsRef.current),
      },
      rightPriceScale: { borderColor: '#262a36' },
      width: container.clientWidth,
      height: initialHeight,
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

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volSeriesRef.current = volSeries;
    setChartApi(chart);

    const applySize = () => {
      if (!containerRef.current || !chartActiveRef.current) return;
      const ch = chartHeightRef.current;
      const h = fillParentHeightRef.current
        ? measureChartFillHeight(containerRef.current, ch)
        : ch;
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: h,
      });
    };

    const ro = new ResizeObserver(applySize);
    ro.observe(container);
    const card = container.closest('.chart-card');
    const portalHost = container.closest('.chart-portal-host');
    if (card) ro.observe(card);
    if (portalHost && portalHost !== card) ro.observe(portalHost);
    requestAnimationFrame(applySize);

    return () => {
      ro.disconnect();
      chart.remove();
      setChartApi(null);
      chartRef.current = null;
      candleSeriesRef.current = null;
      volSeriesRef.current = null;
    };
  }, [containerRef, chartRef, candleSeriesRef, volSeriesRef]);

  useEffect(() => {
    const container = containerRef.current;
    const chart = chartRef.current;
    if (!container || !chart || !chartActive) return;
    const apply = () => {
      if (!containerRef.current || !chartRef.current || !chartActiveRef.current) return;
      const next = fillParentHeightRef.current
        ? measureChartFillHeight(containerRef.current, chartHeightRef.current)
        : chartHeightRef.current;
      chart.applyOptions({ width: containerRef.current.clientWidth, height: next });
    };
    apply();
    requestAnimationFrame(apply);
  }, [
    containerRef,
    chartRef,
    maximized,
    fillParentHeight,
    chartHeight,
    chartActive,
    oscillatorPaneCount,
    layoutEpoch,
  ]);

  return chartApi;
}
