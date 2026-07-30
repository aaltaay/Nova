/** Multi-timeframe chart grid for Trader / Stock View (batch-warmed bars). */
import { useEffect, useMemo, useRef, useState } from 'react';
import { TickerChart, type ChartTradeUpdate } from '../TickerChart';
import { ResizeHandle } from './ResizeHandle';
import { useResizableHeight } from '../hooks/useResizableHeight';
import {
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_OPTIONAL_DEFAULT_ON,
  CHART_GRID_OPTIONAL_PANEL,
  CHART_GRID_OPTIONAL_STORAGE_KEY,
  CHART_GRID_PANE_INDICATORS,
  CHART_GRID_PANELS,
  CHART_TIMEFRAME_BAR_LIMITS,
  STOCK_VIEW_CHART_ROW_SPLIT_KEY,
  STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_PCT,
} from '../constants';
import { ensureBarsBatch } from '../chart/barsStore';

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

  const panels = useMemo(() => {
    if (!showOptional) return CHART_GRID_PANELS;
    return [...CHART_GRID_PANELS, CHART_GRID_OPTIONAL_PANEL];
  }, [showOptional]);

  const topPanels = panels.slice(0, 2);
  const bottomPanels = panels.slice(2);

  useEffect(() => {
    if (!chartActive || !symbol) return;
    // Exclude TFs with a custom bar limit (10Sec) so the pane cold-fetches
    // the full window instead of trusting a batch-trimmed 500-bar entry.
    const tfs = panels
      .map((p) => p.id)
      .filter((id) => !(id in CHART_TIMEFRAME_BAR_LIMITS));
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

  return (
    <div
      ref={gridRef}
      className="chart-grid chart-grid--row-split"
      role="region"
      aria-label="Multi-timeframe charts"
      style={{ ['--chart-row-top-pct' as string]: `${topPct}%` }}
      data-testid="chart-grid"
    >
      <div className="chart-grid__toolbar">
        <button
          type="button"
          className="chart-grid__optional-toggle"
          onClick={toggleOptional}
          aria-pressed={showOptional}
          data-testid="chart-grid-optional-toggle"
        >
          {showOptional ? 'Hide 10-Second' : 'Show 10-Second'}
        </button>
      </div>
      <div className="chart-grid__row chart-grid__row--top">
        {topPanels.map((panel) => (
          <div key={panel.id} className="chart-grid-cell">
            <TickerChart
              symbol={symbol}
              lastTrade={lastTrade}
              variant="grid"
              fixedTimeframe={panel.id}
              title={panel.label}
              subtitle={panel.note}
              initialIndicators={
                CHART_GRID_PANE_INDICATORS[panel.id] ?? CHART_DEFAULT_INDICATORS
              }
              chartActive={chartActive}
            />
          </div>
        ))}
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
        {bottomPanels.map((panel) => (
          <div key={panel.id} className="chart-grid-cell">
            <TickerChart
              symbol={symbol}
              lastTrade={lastTrade}
              variant="grid"
              fixedTimeframe={panel.id}
              title={panel.label}
              subtitle={panel.note}
              initialIndicators={
                CHART_GRID_PANE_INDICATORS[panel.id] ?? CHART_DEFAULT_INDICATORS
              }
              chartActive={chartActive}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
