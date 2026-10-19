/** In-memory drawings for a chart pane that must not write the operator's saved drawings. */

import { useEffect, useRef, type RefObject } from 'react';
import { DrawingManager, type Anchor } from 'lightweight-charts-drawing';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { placeDrawingAtAnchor } from './chartDrawingEvents';
import { bindArmedToolPointer, chartAnchorFromPoint } from './chartDrawingPlace';

interface Options {
  containerRef: RefObject<HTMLDivElement | null>;
  chartRef: RefObject<IChartApi | null>;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  chartApi: IChartApi | null;
  activeTool: string | null;
  /** Bump to wipe this pane's drawings. They are not saved. */
  clearToken?: number;
}

export function useEphemeralDrawings({
  containerRef,
  chartRef,
  candleSeriesRef,
  chartApi,
  activeTool,
  clearToken = 0,
}: Options): void {
  const managerRef = useRef<DrawingManager | null>(null);
  const pendingRef = useRef<Anchor | null>(null);
  const toolRef = useRef(activeTool);
  toolRef.current = activeTool;

  useEffect(() => {
    const container = containerRef.current;
    const series = candleSeriesRef.current;
    const chart = chartRef.current;
    if (!chartApi || !container || !series || !chart) return;

    const manager = new DrawingManager();
    manager.attach(chartApi, series, container);
    managerRef.current = manager;
    const unbind = bindArmedToolPointer(container, () => Boolean(toolRef.current), (point) => {
      const tool = toolRef.current;
      const liveChart = chartRef.current;
      const liveSeries = candleSeriesRef.current;
      if (!tool || !liveChart || !liveSeries) return;
      const anchor = chartAnchorFromPoint(liveChart, liveSeries, point);
      if (!anchor) return;
      placeDrawingAtAnchor({
        tool,
        anchor,
        pendingAnchorRef: pendingRef,
        manager,
        host: container,
        startOrMovePreview: () => {},
        clearPlacePreview: () => {},
      });
    });
    return () => {
      unbind();
      manager.detach();
      managerRef.current = null;
      pendingRef.current = null;
    };
  }, [chartApi, containerRef, chartRef, candleSeriesRef]);

  useEffect(() => {
    pendingRef.current = null;
    managerRef.current?.setActiveTool(activeTool);
    const host = containerRef.current;
    if (host) host.dataset.activeDrawTool = activeTool ?? '';
  }, [activeTool, chartApi, containerRef]);

  useEffect(() => {
    if (!clearToken) return;
    managerRef.current?.clearAll();
    pendingRef.current = null;
  }, [clearToken]);
}
