/**
 * Multi-timeframe chart grid for Trader / Stock View (batch-warmed bars).
 * One desk toolbar above the 2x2 grid owns draw tools (shared) and indicator
 * toggles (focused pane). Panes render a one-line header only.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { TickerChart, type ChartTradeUpdate } from '../TickerChart';
import { ChartGridToolbar } from './ChartGridToolbar';
import { ResizeHandle } from './ResizeHandle';
import { useResizableHeight } from '../hooks/useResizableHeight';
import {
  buildChartGridPanels,
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_OPTIONAL_DEFAULT_ON,
  CHART_GRID_OPTIONAL_STORAGE_KEY,
  CHART_GRID_PANE_INDICATORS,
  CHART_GRID_REGION_ARIA,
  STOCK_VIEW_CHART_ROW_SPLIT_KEY,
  STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_PCT,
  type ChartIndicatorId,
} from '../constants';
import { parseBoolFlag, readPref, writePref } from '../utils/prefStore';
import { ensureBarsBatch } from '../chart/barsStore';
import { clearDrawings, drawingsKey } from '../chart/chartDrawingsStore';
import { toggleIndicator } from '../chartIndicators';
import { useChartGridMaximize } from './useChartGridMaximize';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';

interface Props {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
  /** When false, panes pause refetch/resize (hidden Trader tab). */
  chartActive?: boolean;
}

function readOptionalEnabled(): boolean {
  return readPref(
    CHART_GRID_OPTIONAL_STORAGE_KEY,
    CHART_GRID_OPTIONAL_DEFAULT_ON,
    parseBoolFlag,
  );
}

/** Every pane the grid can show, seeded with its per-timeframe defaults. */
function defaultIndicatorsByPane(): Record<string, ChartIndicatorId[]> {
  return Object.fromEntries(
    buildChartGridPanels(true).map((p) => [
      p.id,
      [...(CHART_GRID_PANE_INDICATORS[p.id] ?? CHART_DEFAULT_INDICATORS)],
    ]),
  );
}

export function ChartGrid({ symbol, lastTrade, chartActive = true }: Props) {
  const gridRef = useRef<HTMLDivElement>(null);
  const { topPct, onDragStart, reset } = useResizableHeight({
    storageKey: STOCK_VIEW_CHART_ROW_SPLIT_KEY,
    defaultPct: STOCK_VIEW_CHART_ROW_SPLIT_PCT,
    minPct: STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
    maxPct: STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
    containerRef: gridRef,
  });
  const sim = useIbkrStatus().mode === 'sim';
  const [showOptional, setShowOptional] = useState(readOptionalEnabled);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [focusedPaneId, setFocusedPaneId] = useState<string | null>(null);
  const [indicatorsByPane, setIndicatorsByPane] = useState(defaultIndicatorsByPane);

  const panels = useMemo(() => buildChartGridPanels(showOptional), [showOptional]);
  const panelIds = useMemo(() => panels.map((p) => p.id), [panels]);
  const { maximizedPaneId, onCellDoubleClick, restore } =
    useChartGridMaximize(panelIds, activeTool, setActiveTool);
  // A hidden 10-Second pane cannot stay the toggle target.
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
    void ensureBarsBatch(symbol, tfs, controller.signal).catch(() => {
      /* panes fetch individually on miss */
    });
    return () => controller.abort();
  }, [symbol, panels, chartActive]);

  const toggleOptional = () => {
    setShowOptional((prev) => {
      const next = !prev;
      writePref(CHART_GRID_OPTIONAL_STORAGE_KEY, next);
      return next;
    });
  };

  const toggleIndicatorFor = (paneId: string, id: ChartIndicatorId) => {
    setIndicatorsByPane((prev) => ({
      ...prev,
      [paneId]: toggleIndicator(prev[paneId] ?? CHART_DEFAULT_INDICATORS, id),
    }));
  };

  const handleToolClick = (toolId: string) => {
    setActiveTool((prev) => (prev === toolId ? null : toolId));
  };

  // Drawings are stored per symbol; every pane rebuilds from the empty set.
  const handleClearAll = () => {
    clearDrawings(drawingsKey(symbol));
    setActiveTool(null);
  };

  const renderPane = (panel: (typeof panels)[number]) => {
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
          lastTrade={lastTrade}
          variant="grid"
          fixedTimeframe={panel.id}
          title={panel.label}
          subtitle={sim && panel.simNote ? panel.simNote : panel.note}
          indicators={indicatorsByPane[panel.id] ?? CHART_DEFAULT_INDICATORS}
          onIndicatorToggle={(id) => toggleIndicatorFor(panel.id, id)}
          activeTool={activeTool}
          onActiveToolChange={setActiveTool}
          compactChrome
          focused={panel.id === focusedPane.id}
          onFocusPane={() => setFocusedPaneId(panel.id)}
          chartActive={chartActive}
          maximizeInGrid
          maximized={paneMaximized}
          layoutEpoch={maximizedPaneId}
        />
      </div>
    );
  };

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
        showOptional={showOptional}
        maximized={Boolean(maximizedPaneId)}
        onToolClick={handleToolClick}
        onClearAll={handleClearAll}
        onIndicatorToggle={(id) => toggleIndicatorFor(focusedPane.id, id)}
        onToggleOptional={toggleOptional}
        onRestore={restore}
      />
      <div className="chart-grid__row chart-grid__row--top">
        {topPanels.map(renderPane)}
      </div>
      <ResizeHandle
        orientation="horizontal"
        onPointerDown={onDragStart}
        onDoubleClick={reset}
        label="Resize chart rows"
      />
      <div
        className={`chart-grid__row chart-grid__row--bottom${
          bottomPanels.length === 1 ? ' chart-grid__row--single' : ''
        }`}
      >
        {bottomPanels.map(renderPane)}
      </div>
    </div>
  );
}
