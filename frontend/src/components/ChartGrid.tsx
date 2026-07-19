/** 2×2 multi-timeframe chart grid for the full trading/detail page. */
import { useRef } from 'react';
import { TickerChart, type ChartTradeUpdate } from '../TickerChart';
import { ResizeHandle } from './ResizeHandle';
import { useResizableHeight } from '../hooks/useResizableHeight';
import {
  CHART_GRID_PANELS,
  STOCK_VIEW_CHART_ROW_SPLIT_KEY,
  STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
  STOCK_VIEW_CHART_ROW_SPLIT_PCT,
} from '../constants';

interface Props {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
}

const TOP_PANELS = CHART_GRID_PANELS.slice(0, 2);
const BOTTOM_PANELS = CHART_GRID_PANELS.slice(2, 4);

export function ChartGrid({ symbol, lastTrade }: Props) {
  const gridRef = useRef<HTMLDivElement>(null);
  const { topPct, onDragStart, reset } = useResizableHeight({
    storageKey: STOCK_VIEW_CHART_ROW_SPLIT_KEY,
    defaultPct: STOCK_VIEW_CHART_ROW_SPLIT_PCT,
    minPct: STOCK_VIEW_CHART_ROW_SPLIT_MIN_PCT,
    maxPct: STOCK_VIEW_CHART_ROW_SPLIT_MAX_PCT,
    containerRef: gridRef,
  });

  return (
    <div
      ref={gridRef}
      className="chart-grid chart-grid--row-split"
      role="region"
      aria-label="Multi-timeframe charts"
      style={{ ['--chart-row-top-pct' as string]: `${topPct}%` }}
      data-testid="chart-grid"
    >
      <div className="chart-grid__row chart-grid__row--top">
        {TOP_PANELS.map((panel) => (
          <div key={panel.id} className="chart-grid-cell">
            <TickerChart
              symbol={symbol}
              lastTrade={lastTrade}
              variant="grid"
              fixedTimeframe={panel.id}
              title={panel.label}
              subtitle={panel.note}
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
      <div className="chart-grid__row chart-grid__row--bottom">
        {BOTTOM_PANELS.map((panel) => (
          <div key={panel.id} className="chart-grid-cell">
            <TickerChart
              symbol={symbol}
              lastTrade={lastTrade}
              variant="grid"
              fixedTimeframe={panel.id}
              title={panel.label}
              subtitle={panel.note}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
