/** The desk chart grid's markup. Live and recorded feeds share it. */

import type { ReactNode, RefObject } from 'react';
import { ChartGridToolbar } from './ChartGridToolbar';
import { ChartToolbarExtra } from './chartToolbarExtra';
import { ResizeHandle } from './ResizeHandle';
import {
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_REGION_ARIA,
  type ChartGridPanel,
  type ChartIndicatorId,
} from '../constants';

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
