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
  STOCK_VIEW_CHART_ROW_SPLIT_KEY,
  STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_PCT,
  type ChartIndicatorId,
} from '../constants';
import { ensureBarsBatch } from '../chart/barsStore';
import { clearDrawings, drawingsKey } from '../chart/chartDrawingsStore';
import { toggleIndicator } from '../chartIndicators';

interface Props {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
  /** When false, panes pause refetch/resize (hidden Trader tab). */
  chartActive?: boolean;
}

function readOptionalEnabled(): boolean {
  try {
    const raw = localStorage.getItem(CHART_GRID_OPTIONAL_STORAGE_KEY);
    if (raw === null) return CHART_GRID_OPTIONAL_DEFAULT_ON;
    return raw !== '0';
  } catch {
    return CHART_GRID_OPTIONAL_DEFAULT_ON;
  }
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
  const [showOptional, setShowOptional] = useState(readOptionalEnabled);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [focusedPaneId, setFocusedPaneId] = useState<string | null>(null);
  const [indicatorsByPane, setIndicatorsByPane] = useState(defaultIndicatorsByPane);

  const panels = useMemo(() => buildChartGridPanels(showOptional), [showOptional]);
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
      try {
        localStorage.setItem(CHART_GRID_OPTIONAL_STORAGE_KEY, next ? '1' : '0');
      } catch {
        /* ignore */
      }
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

  const renderPane = (panel: (typeof panels)[number]) => (
    <div key={panel.id} className="chart-grid-cell">
      <TickerChart
        symbol={symbol}
        lastTrade={lastTrade}
        variant="grid"
        fixedTimeframe={panel.id}
        title={panel.label}
        subtitle={panel.note}
        indicators={indicatorsByPane[panel.id] ?? CHART_DEFAULT_INDICATORS}
        onIndicatorToggle={(id) => toggleIndicatorFor(panel.id, id)}
        activeTool={activeTool}
        onActiveToolChange={setActiveTool}
        compactChrome
        focused={panel.id === focusedPane.id}
        onFocusPane={() => setFocusedPaneId(panel.id)}
        chartActive={chartActive}
      />
    </div>
  );

  return (
    <div
      ref={gridRef}
      className="chart-grid chart-grid--row-split"
      role="region"
      aria-label="Multi-timeframe charts"
      style={{ ['--chart-row-top-pct' as string]: `${topPct}%` }}
      data-testid="chart-grid"
    >
      <ChartGridToolbar
        activeTool={activeTool}
        focusedLabel={focusedPane.label}
        focusedIndicators={indicatorsByPane[focusedPane.id] ?? CHART_DEFAULT_INDICATORS}
        showOptional={showOptional}
        onToolClick={handleToolClick}
        onClearAll={handleClearAll}
        onIndicatorToggle={(id) => toggleIndicatorFor(focusedPane.id, id)}
        onToggleOptional={toggleOptional}
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
