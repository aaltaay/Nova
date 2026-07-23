/** ADR 005 — lightweight-charts instance lifecycle, series refs, and resize. */

import { useEffect, useRef, useState, type RefObject } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
} from 'lightweight-charts';
import { formatChartCrosshairTime, formatChartTickMark } from './chartTimeFormat';
import { measureChartFillHeight } from './measureChartFillHeight';

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
}

export function useChartInstance({
  containerRef,
  chartRef,
  candleSeriesRef,
  volSeriesRef,
  chartHeight,
  fillParentHeight,
  maximized,
}: UseChartInstanceOptions): IChartApi | null {
  const [chartApi, setChartApi] = useState<IChartApi | null>(null);

  const fillParentHeightRef = useRef(fillParentHeight);
  const chartHeightRef = useRef(chartHeight);

  useEffect(() => {
    fillParentHeightRef.current = fillParentHeight;
    chartHeightRef.current = chartHeight;
  }, [fillParentHeight, chartHeight]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialHeight = fillParentHeight
      ? measureChartFillHeight(container, chartHeight)
      : chartHeight;

    const chart = createChart(container, {
      layout: { background: { color: '#161921' }, textColor: '#8b92a5' },
      grid: { vertLines: { color: '#262a36' }, horzLines: { color: '#262a36' } },
      crosshair: {
        vertLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
        horzLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
      },
      localization: {
        locale: 'en-US',
        timeFormatter: formatChartCrosshairTime,
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#262a36',
        tickMarkFormatter: formatChartTickMark,
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
      if (!containerRef.current) return;
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
  }, [
    containerRef,
    chartRef,
    candleSeriesRef,
    volSeriesRef,
    chartHeight,
    fillParentHeight,
  ]);

  useEffect(() => {
    const container = containerRef.current;
    const chart = chartRef.current;
    if (!container || !chart) return;
    const ch = chartHeightRef.current;
    const h = fillParentHeightRef.current
      ? measureChartFillHeight(container, ch)
      : ch;
    chart.applyOptions({ width: container.clientWidth, height: h });
  }, [containerRef, chartRef, maximized, fillParentHeight, chartHeight]);

  return chartApi;
}
