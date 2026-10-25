/** The desk chart grid's markup and the shared pane state. Live and recorded feeds differ only in warm and clear. */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react';
import { TickerChart } from '../TickerChart';
import { ChartGridToolbar } from './ChartGridToolbar';
import { ChartToolbarExtra } from './chartToolbarExtra';
import { ResizeHandle } from './ResizeHandle';
import { useResizableHeight } from '../hooks/useResizableHeight';
import { useChartGridMaximize } from './useChartGridMaximize';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { toggleIndicator } from '../chartIndicators';
import { useChartFeed, type RenderPaneOverlay } from '../chart';
import {
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_PANE_INDICATORS,
  CHART_GRID_REGION_ARIA,
  STOCK_VIEW_CHART_ROW_SPLIT_KEY,
  STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_PCT,
  type ChartIndicatorId,
} from '../constantGroups/chart_api';
import {
  buildChartGridPanels,
  type ChartGridPanel,
} from '../constantGroups/market_ui';

export function ChartGridLayout({
  gridRef,
  topPct,
  onDragStart,
  onResetSplit,
  maximizedPaneId,
  focusedPane,
  topPanels,
  bottomPanels,
  renderPane,
  activeTool,
  indicatorsByPane,
  onToolClick,
  onClearAll,
  onIndicatorToggle,
  onRestore,
  toolbarExtra,
}: {
  gridRef: RefObject<HTMLDivElement | null>;
  topPct: number;
  onDragStart: (event: React.PointerEvent) => void;
  onResetSplit: () => void;
  maximizedPaneId: string | null;
  focusedPane: ChartGridPanel;
  topPanels: ChartGridPanel[];
  bottomPanels: ChartGridPanel[];
  renderPane: (panel: ChartGridPanel) => ReactNode;
  activeTool: string | null;
  indicatorsByPane: Record<string, ChartIndicatorId[]>;
  onToolClick: (toolId: string) => void;
  onClearAll: () => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onRestore: () => void;
  toolbarExtra?: ReactNode;
}) {
  return (
    <div
      ref={gridRef}
      className={`chart-grid chart-grid--row-split${
        maximizedPaneId ? ' chart-grid--pane-maximized' : ''
      }`}
      role="region"
      aria-label={
        maximizedPaneId
          ? `${CHART_GRID_REGION_ARIA}, ${focusedPane.label} maximized`
          : CHART_GRID_REGION_ARIA
      }
      style={{ ['--chart-row-top-pct' as string]: `${topPct}%` }}
      data-testid="chart-grid"
      data-maximized-pane={maximizedPaneId ?? ''}
    >
      <ChartGridToolbar
        activeTool={activeTool}
        focusedLabel={focusedPane.label}
        focusedIndicators={indicatorsByPane[focusedPane.id] ?? CHART_DEFAULT_INDICATORS}
        maximized={Boolean(maximizedPaneId)}
        onToolClick={onToolClick}
        onClearAll={onClearAll}
        onIndicatorToggle={onIndicatorToggle}
        onRestore={onRestore}
        extra={toolbarExtra}
      />
      <ChartToolbarExtra.Provider value={toolbarExtra ?? null}>
        <div className="chart-grid__row chart-grid__row--top">
          {topPanels.map(renderPane)}
        </div>
        <ResizeHandle
          orientation="horizontal"
          onPointerDown={onDragStart}
          onDoubleClick={onResetSplit}
          label="Resize chart rows"
        />
        <div className="chart-grid__row chart-grid__row--bottom">
          {bottomPanels.map(renderPane)}
        </div>
      </ChartToolbarExtra.Provider>
    </div>
  );
}

function defaultIndicatorsByPane(): Record<string, ChartIndicatorId[]> {
  return Object.fromEntries(
    buildChartGridPanels().map((panel) => [
      panel.id,
      [...(CHART_GRID_PANE_INDICATORS[panel.id] ?? CHART_DEFAULT_INDICATORS)],
    ]),
  );
}

/** Shared pane state. `warm` is the live bar prefetch. Recorded grids leave it off. */
export function ChartGridFrame({
  symbol,
  followTicker = false,
  chartActive = true,
  renderPaneOverlay,
  toolbarExtra,
  panels: panelsProp,
  warm,
  onClearDrawings,
}: {
  symbol: string;
  followTicker?: boolean;
  chartActive?: boolean;
  renderPaneOverlay?: RenderPaneOverlay;
  toolbarExtra?: ReactNode;
  panels?: ChartGridPanel[];
  warm: boolean;
  onClearDrawings: (symbol: string) => void;
}) {
  const gridRef = useRef<HTMLDivElement>(null);
  const { topPct, onDragStart, reset } = useResizableHeight({
    storageKey: STOCK_VIEW_CHART_ROW_SPLIT_KEY,
    defaultPct: STOCK_VIEW_CHART_ROW_SPLIT_PCT,
    minPct: STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
    maxPct: STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
    containerRef: gridRef,
  });
  const sim = useIbkrStatus().mode === 'sim';
  const feed = useChartFeed();
  const subtitleFor = (panel: ChartGridPanel): string | undefined => {
    if (feed.kind === 'recorded') return feed.notes?.[panel.id as keyof NonNullable<typeof feed.notes>];
    return sim && panel.simNote ? panel.simNote : panel.note;
  };
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [focusedPaneId, setFocusedPaneId] = useState<string | null>(null);
  const [indicatorsByPane, setIndicatorsByPane] = useState(defaultIndicatorsByPane);

  const built = useMemo(() => buildChartGridPanels(), []);
  const panels = panelsProp ?? built;
  const panelIds = useMemo(() => panels.map((panel) => panel.id), [panels]);
  const { maximizedPaneId, onCellDoubleClick, restore } =
    useChartGridMaximize(panelIds, activeTool, setActiveTool);
  const focusedPane = panels.find((panel) => panel.id === focusedPaneId) ?? panels[0];
  const topPanels = panels.slice(0, 2);
  const bottomPanels = panels.slice(2);

  useEffect(() => {
    if (!warm || !chartActive || !symbol) return;
    const timeframes = panels.map((panel) => panel.id);
    if (timeframes.length === 0) return;
    const controller = new AbortController();
    let cancelled = false;
    void import('../chart/barsStore').then(({ ensureBarsBatch }) => {
      if (cancelled) return;
      return ensureBarsBatch(symbol, timeframes, controller.signal).catch((err) => {
        if (!controller.signal.aborted) {
          console.warn(
            `ChartGrid batch warm failed for ${symbol}; panes will fetch individually:`,
            err,
          );
        }
      });
    }).catch((err) => {
      if (!cancelled) {
        console.warn(
          `ChartGrid batch warm failed for ${symbol}; panes will fetch individually:`,
          err,
        );
      }
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [warm, symbol, panels, chartActive]);

  const toggleIndicatorFor = useCallback((paneId: string, id: ChartIndicatorId) => {
    setIndicatorsByPane((prev) => ({
      ...prev,
      [paneId]: toggleIndicator(prev[paneId] ?? CHART_DEFAULT_INDICATORS, id),
    }));
  }, []);
  const paneHandlers = useMemo(
    () =>
      Object.fromEntries(
        panels.map((panel) => [
          panel.id,
          {
            onIndicatorToggle: (id: ChartIndicatorId) => toggleIndicatorFor(panel.id, id),
            onFocusPane: () => setFocusedPaneId(panel.id),
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
          subtitle={subtitleFor(panel)}
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
      onToolClick={(toolId) => setActiveTool((prev) => (prev === toolId ? null : toolId))}
      onClearAll={() => {
        onClearDrawings(symbol);
        setActiveTool(null);
      }}
      onIndicatorToggle={(id) => toggleIndicatorFor(focusedPane.id, id)}
      onRestore={restore}
      toolbarExtra={toolbarExtra}
    />
  );
}
