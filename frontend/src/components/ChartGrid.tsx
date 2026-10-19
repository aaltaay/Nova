/**
 * Multi-timeframe chart grid for Trader / Stock View (batch-warmed bars).
 * One desk toolbar above the 2x2 grid owns draw tools (shared) and indicator
 * toggles (focused pane). Panes render a one-line header only; a pane in full screen shows its own toolbar, with the
 * desk toolbar's extra (the Eyes switch) in it too (`chartToolbarExtra.ts`).
 */
import { memo, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { TickerChart } from '../TickerChart';
import { ChartGridLayout } from './ChartGridLayout';
import { useResizableHeight } from '../hooks/useResizableHeight';
import {
  buildChartGridPanels,
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_PANE_INDICATORS,
  STOCK_VIEW_CHART_ROW_SPLIT_KEY,
  STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_PCT,
  type ChartGridPanel,
  type ChartIndicatorId,
} from '../constants';
import { ensureBarsBatch } from '../chart/barsStore';
import { clearDrawings, drawingsKey } from '../chart/chartDrawingsStore';
import { toggleIndicator } from '../chartIndicators';
import { useChartGridMaximize } from './useChartGridMaximize';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { useChartFeed, useClearRecordedDrawings } from '../chart';
import type { RenderPaneOverlay } from '../chart';

interface Props {
  symbol: string;
  /** Each pane follows the ticker stream itself (the Trader tab): a print draws the live candle without
   * rendering the grid (#707). */
  followTicker?: boolean;
  /** When false, panes pause refetch/resize (hidden Trader tab). */
  chartActive?: boolean;
  /** Drawn inside every pane (the Trader tab's stock read, ADR 036). */
  renderPaneOverlay?: RenderPaneOverlay;
  /** Extra switches on the desk toolbar. */
  toolbarExtra?: ReactNode;
  /** Defaults to the desk 2x2. A caller can pass a shorter list. */
  panels?: ChartGridPanel[];
}

/** Every pane the grid can show, seeded with its per-timeframe defaults. */
function defaultIndicatorsByPane(): Record<string, ChartIndicatorId[]> {
  return Object.fromEntries(
    buildChartGridPanels().map((p) => [
      p.id,
      [...(CHART_GRID_PANE_INDICATORS[p.id] ?? CHART_DEFAULT_INDICATORS)],
    ]),
  );
}

/** Memoized with its panes (see TickerChart): the Trader page re-renders far more often than a chart changes. */
export const ChartGrid = memo(function ChartGrid(props: Props) {
  const feed = useChartFeed();
  if (feed.kind === 'recorded') return <RecordedChartGrid {...props} />;
  return <LiveChartGrid {...props} />;
});

function LiveChartGrid({
  symbol, followTicker = false, chartActive = true, renderPaneOverlay, toolbarExtra, panels: panelsProp,
}: Props) {
  const gridRef = useRef<HTMLDivElement>(null);
  const { topPct, onDragStart, reset } = useResizableHeight({
    storageKey: STOCK_VIEW_CHART_ROW_SPLIT_KEY,
    defaultPct: STOCK_VIEW_CHART_ROW_SPLIT_PCT,
    minPct: STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
    maxPct: STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
    containerRef: gridRef,
  });
  const sim = useIbkrStatus().mode === 'sim';
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [focusedPaneId, setFocusedPaneId] = useState<string | null>(null);
  const [indicatorsByPane, setIndicatorsByPane] = useState(defaultIndicatorsByPane);

  const built = useMemo(() => buildChartGridPanels(), []);
  const panels = panelsProp ?? built;
  const panelIds = useMemo(() => panels.map((p) => p.id), [panels]);
  const { maximizedPaneId, onCellDoubleClick, restore } =
    useChartGridMaximize(panelIds, activeTool, setActiveTool);
  const focusedPane =
    panels.find((p) => p.id === focusedPaneId) ?? panels[0];

  const topPanels = panels.slice(0, 2);
  const bottomPanels = panels.slice(2);

  useEffect(() => {
    if (!chartActive || !symbol) return;
    // Parallel store-first /bars. Include 10Sec so it uses CHART_TIMEFRAME_BAR_LIMITS.
    const tfs = panels.map((p) => p.id);
    if (tfs.length === 0) return;
    const controller = new AbortController();
    void ensureBarsBatch(symbol, tfs, controller.signal).catch((err) => {
      if (!controller.signal.aborted) {
        console.warn(`ChartGrid batch warm failed for ${symbol}; panes will fetch individually:`, err);
      }
    });
    return () => controller.abort();
  }, [symbol, panels, chartActive]);

  const toggleIndicatorFor = useCallback((paneId: string, id: ChartIndicatorId) => {
    setIndicatorsByPane((prev) => ({
      ...prev,
      [paneId]: toggleIndicator(prev[paneId] ?? CHART_DEFAULT_INDICATORS, id),
    }));
  }, []);
  // One handler per pane that lives as long as the pane list, so a memoized pane is not drawn
  // again for a new arrow function.
  const paneHandlers = useMemo(
    () =>
      Object.fromEntries(
        panels.map((p) => [
          p.id,
          {
            onIndicatorToggle: (id: ChartIndicatorId) => toggleIndicatorFor(p.id, id),
            onFocusPane: () => setFocusedPaneId(p.id),
          },
        ]),
      ),
    [panels, toggleIndicatorFor],
  );

  const handleToolClick = (toolId: string) => {
    setActiveTool((prev) => (prev === toolId ? null : toolId));
  };

  // Drawings are stored per symbol; every pane rebuilds from the empty set.
  const handleClearAll = () => {
    clearDrawings(drawingsKey(symbol));
    setActiveTool(null);
  };

  const renderPane = (panel: ChartGridPanel) => {
    const paneMaximized = maximizedPaneId === panel.id;
    return (
      <div
        key={panel.id}
        className={`chart-grid-cell${paneMaximized ? ' chart-grid-cell--maximized' : ''}`}
        data-testid={`chart-grid-cell-${panel.id}`}
        data-maximized={paneMaximized ? '1' : '0'}
        onDoubleClick={(event) => {
          setFocusedPaneId(panel.id);
          onCellDoubleClick(panel.id, event);
        }}
      >
        <TickerChart
          symbol={symbol}
          followTicker={followTicker}
          variant="grid"
          fixedTimeframe={panel.id}
          title={panel.label}
          subtitle={sim && panel.simNote ? panel.simNote : panel.note}
          indicators={indicatorsByPane[panel.id] ?? CHART_DEFAULT_INDICATORS}
          onIndicatorToggle={paneHandlers[panel.id]?.onIndicatorToggle}
          activeTool={activeTool}
          onActiveToolChange={setActiveTool}
          compactChrome
          focused={panel.id === focusedPane.id}
          onFocusPane={paneHandlers[panel.id]?.onFocusPane}
          chartActive={chartActive}
          maximizeInGrid
          maximized={paneMaximized}
          layoutEpoch={maximizedPaneId}
          renderPaneOverlay={renderPaneOverlay}
        />
      </div>
    );
  };

  return (
    <ChartGridLayout
      gridRef={gridRef}
      topPct={topPct}
      onDragStart={onDragStart}
      onResetSplit={reset}
      maximizedPaneId={maximizedPaneId}
      focusedPane={focusedPane}
      topPanels={topPanels}
      bottomPanels={bottomPanels}
      renderPane={renderPane}
      activeTool={activeTool}
      indicatorsByPane={indicatorsByPane}
      onToolClick={handleToolClick}
      onClearAll={handleClearAll}
      onIndicatorToggle={(id) => toggleIndicatorFor(focusedPane.id, id)}
      onRestore={restore}
      toolbarExtra={toolbarExtra}
    />
  );
}

function RecordedChartGrid({
  symbol, followTicker = false, chartActive = true, renderPaneOverlay, toolbarExtra, panels: panelsProp,
}: Props) {
  const gridRef = useRef<HTMLDivElement>(null);
  const { topPct, onDragStart, reset } = useResizableHeight({
    storageKey: STOCK_VIEW_CHART_ROW_SPLIT_KEY,
    defaultPct: STOCK_VIEW_CHART_ROW_SPLIT_PCT,
    minPct: STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
    maxPct: STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
    containerRef: gridRef,
  });
  const sim = useIbkrStatus().mode === 'sim';
  const clearRecorded = useClearRecordedDrawings();
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [focusedPaneId, setFocusedPaneId] = useState<string | null>(null);
  const [indicatorsByPane, setIndicatorsByPane] = useState(defaultIndicatorsByPane);
  const built = useMemo(() => buildChartGridPanels(), []);
  const panels = panelsProp ?? built;
  const panelIds = useMemo(() => panels.map((p) => p.id), [panels]);
  const { maximizedPaneId, onCellDoubleClick, restore } =
    useChartGridMaximize(panelIds, activeTool, setActiveTool);
  const focusedPane = panels.find((p) => p.id === focusedPaneId) ?? panels[0];
  const toggleIndicatorFor = useCallback((paneId: string, id: ChartIndicatorId) => {
    setIndicatorsByPane((prev) => ({
      ...prev,
      [paneId]: toggleIndicator(prev[paneId] ?? CHART_DEFAULT_INDICATORS, id),
    }));
  }, []);
  const paneHandlers = useMemo(
    () =>
      Object.fromEntries(
        panels.map((p) => [
          p.id,
          {
            onIndicatorToggle: (id: ChartIndicatorId) => toggleIndicatorFor(p.id, id),
            onFocusPane: () => setFocusedPaneId(p.id),
          },
        ]),
      ),
    [panels, toggleIndicatorFor],
  );
  const renderPane = (panel: ChartGridPanel) => {
    const paneMaximized = maximizedPaneId === panel.id;
    return (
      <div
        key={panel.id}
        className={`chart-grid-cell${paneMaximized ? ' chart-grid-cell--maximized' : ''}`}
        data-testid={`chart-grid-cell-${panel.id}`}
        data-maximized={paneMaximized ? '1' : '0'}
        onDoubleClick={(event) => {
          setFocusedPaneId(panel.id);
          onCellDoubleClick(panel.id, event);
        }}
      >
        <TickerChart
          symbol={symbol}
          followTicker={followTicker}
          variant="grid"
          fixedTimeframe={panel.id}
          title={panel.label}
          subtitle={sim && panel.simNote ? panel.simNote : panel.note}
          indicators={indicatorsByPane[panel.id] ?? CHART_DEFAULT_INDICATORS}
          onIndicatorToggle={paneHandlers[panel.id]?.onIndicatorToggle}
          activeTool={activeTool}
          onActiveToolChange={setActiveTool}
          compactChrome
          focused={panel.id === focusedPane.id}
          onFocusPane={paneHandlers[panel.id]?.onFocusPane}
          chartActive={chartActive}
          maximizeInGrid
          maximized={paneMaximized}
          layoutEpoch={maximizedPaneId}
          renderPaneOverlay={renderPaneOverlay}
        />
      </div>
    );
  };
  return (
    <ChartGridLayout
      gridRef={gridRef}
      topPct={topPct}
      onDragStart={onDragStart}
      onResetSplit={reset}
      maximizedPaneId={maximizedPaneId}
      focusedPane={focusedPane}
      topPanels={panels.slice(0, 2)}
      bottomPanels={panels.slice(2)}
      renderPane={renderPane}
      activeTool={activeTool}
      indicatorsByPane={indicatorsByPane}
      onToolClick={(toolId) => setActiveTool((prev) => (prev === toolId ? null : toolId))}
      onClearAll={() => {
        clearRecorded();
        setActiveTool(null);
      }}
      onIndicatorToggle={(id) => toggleIndicatorFor(focusedPane.id, id)}
      onRestore={restore}
      toolbarExtra={toolbarExtra}
    />
  );
}
