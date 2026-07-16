/** ADR 005 — drawing-manager attach/detach and active-tool interaction. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { DrawingManager, TrendLine, type Anchor } from 'lightweight-charts-drawing';
import type { IChartApi, ISeriesApi, MouseEventParams, Time } from 'lightweight-charts';
import { CHART_DRAWING_STYLE, CHART_SINGLE_ANCHOR_TOOLS } from './chartDrawingConfig';
interface UseChartDrawingManagerOptions {
  containerRef: React.RefObject<HTMLDivElement | null>;
  chartRef: React.RefObject<IChartApi | null>;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  chartApi: IChartApi | null;
}

export function useChartDrawingManager({
  containerRef,
  chartApi,
  chartRef,
  candleSeriesRef,
}: UseChartDrawingManagerOptions) {
  const managerRef = useRef<DrawingManager | null>(null);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const activeToolRef = useRef<string | null>(null);
  const pendingAnchorRef = useRef<Anchor | null>(null);

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
      manager.addDrawing(new TrendLine(`trendline-${Date.now()}`, [pending, anchor], CHART_DRAWING_STYLE));
      pendingAnchorRef.current = null;
      return;
    }

    const DrawingClass = CHART_SINGLE_ANCHOR_TOOLS[tool];
    if (DrawingClass) {
      manager.addDrawing(new DrawingClass(`${tool.toLowerCase()}-${Date.now()}`, [anchor], CHART_DRAWING_STYLE));
    }
  }, [chartRef, candleSeriesRef]);

  useEffect(() => {
    const container = containerRef.current;
    const candleSeries = candleSeriesRef.current;
    const chart = chartRef.current;
    if (!chartApi || !container || !candleSeries || !chart) return;

    const manager = new DrawingManager();
    manager.attach(chartApi, candleSeries, container);
    managerRef.current = manager;
    chart.subscribeClick(handleChartClick);

    return () => {
      chart.unsubscribeClick(handleChartClick);
      manager.detach();
      managerRef.current = null;
    };
  }, [chartApi, containerRef, candleSeriesRef, chartRef, handleChartClick]);

  useEffect(() => {
    activeToolRef.current = activeTool;
    pendingAnchorRef.current = null;
    managerRef.current?.setActiveTool(activeTool);
    if (containerRef.current) {
      containerRef.current.style.cursor = activeTool ? 'crosshair' : 'default';
    }
  }, [activeTool, containerRef]);

  useEffect(() => {
    const manager = managerRef.current;
    if (!manager) return;
    const unsub = manager.on('drawing:added', () => {
      setActiveTool(null);
    });
    return unsub;
  }, [chartApi]);

  function handleToolClick(toolId: string) {
    setActiveTool(prev => (prev === toolId ? null : toolId));
  }

  function handleClearAll() {
    managerRef.current?.clearAll();
    setActiveTool(null);
  }

  return {
    activeTool,
    setActiveTool,
    handleChartClick,
    handleToolClick,
    handleClearAll,
  };
}
