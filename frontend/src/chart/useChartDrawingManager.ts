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
  type Anchor,
  type IDrawing,
} from 'lightweight-charts-drawing';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import {
  CHART_DRAWING_STYLE,
  CHART_SINGLE_ANCHOR_TOOLS,
  CHART_TWO_ANCHOR_TOOLS,
} from './chartDrawingConfig';
export type { DrawingSelectionState } from './chartDrawingColor';
import { applyChartHostInteraction } from './chartDrawingInteraction';
import { bindHandleEditPointer } from './chartDrawingHandle';
import {
  attachPlacePreview,
  bindPlacePreviewPointer,
  createPlacePreviewDrawing,
  detachPlacePreview,
  markPlacePreviewHost,
  movePlacePreview,
  shouldShowPlacePreview,
} from './chartDrawingPreview';
import {
  bindArmedToolPointer,
  chartAnchorFromPoint,
  placeArmedToolClick,
  type ChartPlacePoint,
} from './chartDrawingPlace';
import {
  deleteSelectedDrawingOnKey,
  ownsChartDrawingHotkeyFocus,
  releaseChartDrawingHotkeyFocus,
  resolveChartDrawingHotkey,
} from './chartDrawingKeys';
import { toStorableDrawing } from './chartDrawingTime';
import {
  drawingFactory,
  seriesTimeIndex,
  shouldDisarmToolOnDrawingAdded,
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
import {
  selectionStateFromDrawing,
  applyDrawingColor,
  type DrawingSelectionState,
} from './chartDrawingColor';

interface UseChartDrawingManagerOptions {
  containerRef: React.RefObject<HTMLDivElement | null>;
  chartRef: React.RefObject<IChartApi | null>;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  chartApi: IChartApi | null;
  /** Drawings are stored per symbol -- panes on other symbols must not see them. */
  symbol: string;
  /** Bumps when this pane repaints its series, so anchors can re-snap. */
  seriesRevision?: number;
  /** Only the last interacted chart pane may consume line-tool hotkeys. */
  hotkeyOwner: symbol;
  /**
   * Controlled active tool (Trader grid shares one tool across all panes so a
   * single desk toolbar drives every chart). Omit for per-pane local state.
   */
  activeTool?: string | null;
  onActiveToolChange?: (tool: string | null) => void;
}

export function useChartDrawingManager({
  containerRef,
  chartApi,
  chartRef,
  candleSeriesRef,
  symbol,
  seriesRevision = 0,
  hotkeyOwner,
  activeTool: controlledTool,
  onActiveToolChange,
}: UseChartDrawingManagerOptions) {
  const managerRef = useRef<DrawingManager | null>(null);
  const [localTool, setLocalTool] = useState<string | null>(null);
  const controlled = controlledTool !== undefined;
  const activeTool = controlled ? controlledTool : localTool;
  const activeToolRef = useRef<string | null>(null);
  const onToolChangeRef = useRef(onActiveToolChange);
  onToolChangeRef.current = onActiveToolChange;
  const setActiveTool = useCallback(
    (next: string | null | ((prev: string | null) => string | null)) => {
      if (controlled) {
        const resolved = typeof next === 'function' ? next(activeToolRef.current) : next;
        onToolChangeRef.current?.(resolved);
        return;
      }
      setLocalTool(next);
    },
    [controlled],
  );
  const pendingAnchorRef = useRef<Anchor | null>(null);
  const previewDrawingRef = useRef<IDrawing | null>(null);
  const editingHandleRef = useRef(false);
  const symbolRef = useRef(drawingsKey(symbol));
  /** True while rebuilding from the store -- suppresses our own echo writes. */
  const applyingRef = useRef(false);
  const hydratedRef = useRef<HydrateState | null>(null);
  const [storeTick, setStoreTick] = useState(0);
  /** Bumped on every attach so listener and hydrate effects follow the new manager. */
  const [managerEpoch, setManagerEpoch] = useState(0);
  const [selection, setSelection] = useState<DrawingSelectionState | null>(null);

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

  const clearPlacePreview = useCallback(() => {
    detachPlacePreview(previewDrawingRef.current);
    previewDrawingRef.current = null;
    markPlacePreviewHost(containerRef.current, false);
  }, [containerRef]);

  const applyInteraction = useCallback(() => {
    applyChartHostInteraction(
      containerRef.current,
      chartRef.current,
      activeToolRef.current,
      editingHandleRef.current,
    );
  }, [containerRef, chartRef]);

  const startOrMovePreview = useCallback((start: Anchor, cursor: Anchor) => {
    const tool = activeToolRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    const host = containerRef.current;
    if (!tool || !chart || !series || !host) return;
    if (!shouldShowPlacePreview(tool, start)) {
      clearPlacePreview();
      return;
    }
    let preview = previewDrawingRef.current;
    if (!preview) {
      preview = createPlacePreviewDrawing(tool, start, cursor);
      if (!preview) return;
      attachPlacePreview(preview, series, chart, host);
      previewDrawingRef.current = preview;
    } else {
      movePlacePreview(preview, cursor);
    }
    markPlacePreviewHost(host, true);
  }, [chartRef, candleSeriesRef, containerRef, clearPlacePreview]);

  const placeFromPoint = useCallback((point: ChartPlacePoint) => {
    const tool = activeToolRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    const manager = managerRef.current;
    if (!tool || !manager || !chart || !series) return;

    const anchor = chartAnchorFromPoint(chart, series, point);
    if (!anchor) return;
    const result = placeArmedToolClick({
      tool,
      pending: pendingAnchorRef.current,
      anchor,
      twoAnchorTool: Boolean(CHART_TWO_ANCHOR_TOOLS[tool]),
      singleAnchorTool: Boolean(CHART_SINGLE_ANCHOR_TOOLS[tool]),
    });
    pendingAnchorRef.current = result.pending;
    if (result.action === 'wait') {
      startOrMovePreview(anchor, anchor);
    } else if (result.action === 'two') {
      clearPlacePreview();
      const DrawingClass = CHART_TWO_ANCHOR_TOOLS[tool];
      if (!DrawingClass) return;
      manager.addDrawing(
        new DrawingClass(`${tool.toLowerCase()}-${Date.now()}`, result.anchors, CHART_DRAWING_STYLE),
      );
    } else if (result.action === 'one') {
      clearPlacePreview();
      const DrawingClass = CHART_SINGLE_ANCHOR_TOOLS[tool];
      if (!DrawingClass) return;
      manager.addDrawing(
        new DrawingClass(`${tool.toLowerCase()}-${Date.now()}`, result.anchors, CHART_DRAWING_STYLE),
      );
    }
    const host = containerRef.current;
    if (host) host.dataset.drawingCount = String(manager.getAllDrawings().length);
  }, [chartRef, candleSeriesRef, containerRef, startOrMovePreview, clearPlacePreview]);

  const previewFromPoint = useCallback((point: ChartPlacePoint) => {
    const pending = pendingAnchorRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    if (!pending || !chart || !series) return;
    const cursor = chartAnchorFromPoint(chart, series, point);
    if (!cursor) return;
    startOrMovePreview(pending, cursor);
  }, [chartRef, candleSeriesRef, startOrMovePreview]);

  useEffect(() => {
    const container = containerRef.current;
    const candleSeries = candleSeriesRef.current;
    const chart = chartRef.current;
    if (!chartApi || !container || !candleSeries || !chart) return;

    const manager = new DrawingManager();
    manager.attach(chartApi, candleSeries, container);
    managerRef.current = manager;
    const unbindPlace = bindArmedToolPointer(
      container,
      () => Boolean(activeToolRef.current),
      placeFromPoint,
    );
    const unbindPreview = bindPlacePreviewPointer(
      container,
      () => shouldShowPlacePreview(activeToolRef.current, pendingAnchorRef.current),
      previewFromPoint,
    );
    const unbindHandle = bindHandleEditPointer(
      container,
      () => managerRef.current,
      () => Boolean(activeToolRef.current),
      (editing) => {
        editingHandleRef.current = editing;
        applyInteraction();
      },
    );
    setManagerEpoch(e => e + 1);

    return () => {
      unbindPlace();
      unbindPreview();
      unbindHandle();
      clearPlacePreview();
      manager.detach();
      managerRef.current = null;
      hydratedRef.current = null;
    };
  }, [
    chartApi,
    containerRef,
    candleSeriesRef,
    chartRef,
    placeFromPoint,
    previewFromPoint,
    applyInteraction,
    clearPlacePreview,
  ]);

  // Load this symbol's stored set and follow every later change to it.
  useEffect(() => {
    pendingAnchorRef.current = null;
    editingHandleRef.current = false;
    clearPlacePreview();
    applyInteraction();
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
  }, [symbol, clearPlacePreview, applyInteraction]);

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
    const host = containerRef.current;
    if (host) host.dataset.drawingCount = String(manager.getAllDrawings().length);
  }, [symbol, storeTick, seriesRevision, managerEpoch, candleSeriesRef, containerRef]);

  useEffect(() => {
    activeToolRef.current = activeTool;
    pendingAnchorRef.current = null;
    editingHandleRef.current = false;
    clearPlacePreview();
    managerRef.current?.setActiveTool(activeTool);
    if (activeTool) managerRef.current?.deselectAll();
    if (activeTool) setSelection(null);
    if (containerRef.current) {
      containerRef.current.style.cursor = activeTool ? 'crosshair' : 'default';
      containerRef.current.dataset.activeDrawTool = activeTool ?? '';
    }
    applyInteraction();
  }, [activeTool, containerRef, applyInteraction, clearPlacePreview]);

  useEffect(() => {
    const manager = managerRef.current;
    if (!manager) return;

    const unsubAdded = manager.on('drawing:added', (event) => {
      if (shouldDisarmToolOnDrawingAdded(applyingRef.current)) {
        setActiveTool(null);
      }
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
    const unsubSelected = manager.on('drawing:selected', (event) => {
      setSelection(selectionStateFromDrawing(event.drawing));
    });
    const unsubDeselected = manager.on('drawing:deselected', () => {
      setSelection(null);
    });

    const onDeleteKey = (event: KeyboardEvent) => {
      const current = managerRef.current;
      if (!current) return;
      if (deleteSelectedDrawingOnKey(current, event)) return;
      if (!ownsChartDrawingHotkeyFocus(hotkeyOwner)) return;
      const tool = resolveChartDrawingHotkey(event);
      if (!tool) return;
      event.preventDefault();
      setActiveTool(tool);
    };
    window.addEventListener('keydown', onDeleteKey);
    return () => {
      unsubAdded();
      unsubUpdated();
      unsubRemoved();
      unsubSelected();
      unsubDeselected();
      window.removeEventListener('keydown', onDeleteKey);
      releaseChartDrawingHotkeyFocus(hotkeyOwner);
    };
  }, [hotkeyOwner, managerEpoch, persist, setActiveTool, storeDrawing]);

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

  const updateSelectedDrawingColor = useCallback((color: string) => {
    const manager = managerRef.current;
    if (!manager) return;
    const drawing = manager.getSelectedDrawing();
    if (!drawing) return;
    setSelection(applyDrawingColor(drawing, color, symbolRef.current, persist));
  }, [persist]);

  return {
    activeTool,
    setActiveTool,
    handleToolClick,
    handleClearAll,
    selection,
    updateSelectedDrawingColor,
  };
}
