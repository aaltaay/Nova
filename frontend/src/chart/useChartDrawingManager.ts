/**
 * ADR 005 — drawing-manager attach/detach and active-tool interaction.
 * ADR 015 — drawings are shared across every timeframe pane and persisted.
 *
 * The manager itself stays per-pane (it owns hit testing against one canvas),
 * but its contents come from `chartDrawingsStore` keyed by symbol. So a level
 * drawn on the 1Min pane appears on 5m/1D/Quote Panel, and survives a reload.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DrawingManager,
  TrendLine,
  type Anchor,
  type IDrawing,
} from 'lightweight-charts-drawing';
import type { IChartApi, ISeriesApi, MouseEventParams, Time } from 'lightweight-charts';
import { CHART_DRAWING_STYLE, CHART_SINGLE_ANCHOR_TOOLS } from './chartDrawingConfig';
import { deleteSelectedDrawingOnKey } from './chartDrawingKeys';
import { toStorableDrawing } from './chartDrawingTime';
import {
  drawingFactory,
  seriesTimeIndex,
  shouldHydrateDrawings,
  snapAll,
  type HydrateState,
} from './chartDrawingHydrate';
import {
  clearDrawings,
  drawingsKey,
  ensureDrawings,
  getDrawings,
  refreshDrawings,
  removeDrawing,
  revisionOf,
  subscribeDrawings,
  upsertDrawing,
} from './chartDrawingsStore';

interface UseChartDrawingManagerOptions {
  containerRef: React.RefObject<HTMLDivElement | null>;
  chartRef: React.RefObject<IChartApi | null>;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  chartApi: IChartApi | null;
  /** Drawings are stored per symbol -- panes on other symbols must not see them. */
  symbol: string;
  /** Bumps when this pane repaints its series, so anchors can re-snap. */
  seriesRevision?: number;
}

export function useChartDrawingManager({
  containerRef,
  chartApi,
  chartRef,
  candleSeriesRef,
  symbol,
  seriesRevision = 0,
}: UseChartDrawingManagerOptions) {
  const managerRef = useRef<DrawingManager | null>(null);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const activeToolRef = useRef<string | null>(null);
  const pendingAnchorRef = useRef<Anchor | null>(null);
  const symbolRef = useRef(drawingsKey(symbol));
  /** True while rebuilding from the store -- suppresses our own echo writes. */
  const applyingRef = useRef(false);
  const hydratedRef = useRef<HydrateState | null>(null);
  const [storeTick, setStoreTick] = useState(0);
  /** Bumped on every attach so listener and hydrate effects follow the new manager. */
  const [managerEpoch, setManagerEpoch] = useState(0);

  symbolRef.current = drawingsKey(symbol);

  /** Run a store mutation, then claim its revision so we do not re-import it. */
  const persist = useCallback((mutate: () => void) => {
    mutate();
    const state = hydratedRef.current;
    if (state && state.symbol === symbolRef.current) {
      state.revision = revisionOf(symbolRef.current);
    }
  }, []);

  const storeDrawing = useCallback((drawing: IDrawing | undefined) => {
    if (applyingRef.current || !drawing) return;
    const storable = toStorableDrawing(drawing.toJSON());
    if (!storable) return;
    persist(() => upsertDrawing(symbolRef.current, storable));
  }, [persist]);

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
    setManagerEpoch(e => e + 1);

    return () => {
      chart.unsubscribeClick(handleChartClick);
      manager.detach();
      managerRef.current = null;
      hydratedRef.current = null;
    };
  }, [chartApi, containerRef, candleSeriesRef, chartRef, handleChartClick]);

  // Load this symbol's stored set and follow every later change to it.
  useEffect(() => {
    const key = drawingsKey(symbol);
    if (!key) return;
    void ensureDrawings(key);
    const unsubscribe = subscribeDrawings(key, () => setStoreTick(t => t + 1));
    // A detached Trader window is its own renderer -- resync when it regains focus.
    const onFocus = () => { void refreshDrawings(key); };
    window.addEventListener('focus', onFocus);
    return () => {
      unsubscribe();
      window.removeEventListener('focus', onFocus);
    };
  }, [symbol]);

  // Rebuild the pane's drawings, snapped onto this timeframe's bar grid.
  useEffect(() => {
    const manager = managerRef.current;
    if (!manager) return;
    const key = drawingsKey(symbol);
    const index = seriesTimeIndex(candleSeriesRef.current);
    const target = { symbol: key, revision: revisionOf(key), hasBars: index.times.length > 0 };
    if (!shouldHydrateDrawings(hydratedRef.current, target)) return;

    applyingRef.current = true;
    try {
      manager.clearAll();
      manager.importDrawings(snapAll(getDrawings(key), index), drawingFactory);
    } finally {
      applyingRef.current = false;
    }
    hydratedRef.current = { symbol: key, revision: target.revision, hadBars: target.hasBars };
  }, [symbol, storeTick, seriesRevision, managerEpoch, candleSeriesRef]);

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

    const unsubAdded = manager.on('drawing:added', (event) => {
      setActiveTool(null);
      storeDrawing(event.drawing);
    });
    // Fires per mousemove while dragging an anchor; the store debounces the PUT.
    const unsubUpdated = manager.on('drawing:updated', (event) => {
      storeDrawing(event.drawing);
    });
    const unsubRemoved = manager.on('drawing:removed', (event) => {
      const id = event.drawingId;
      if (applyingRef.current || !id) return;
      persist(() => removeDrawing(symbolRef.current, id));
    });

    const onDeleteKey = (event: KeyboardEvent) => {
      const current = managerRef.current;
      if (!current) return;
      deleteSelectedDrawingOnKey(current, event);
    };
    window.addEventListener('keydown', onDeleteKey);
    return () => {
      unsubAdded();
      unsubUpdated();
      unsubRemoved();
      window.removeEventListener('keydown', onDeleteKey);
    };
  }, [managerEpoch, persist, storeDrawing]);

  function handleToolClick(toolId: string) {
    setActiveTool(prev => (prev === toolId ? null : toolId));
  }

  function handleClearAll() {
    const manager = managerRef.current;
    // clearAll emits drawing:cleared per drawing-free semantics; suppress the
    // echo and issue one explicit DELETE instead of N removes.
    applyingRef.current = true;
    try {
      manager?.clearAll();
    } finally {
      applyingRef.current = false;
    }
    // Clears every pane on this symbol, not just the one that was clicked.
    persist(() => clearDrawings(symbolRef.current));
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
