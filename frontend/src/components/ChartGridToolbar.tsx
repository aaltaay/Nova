/**
 * One desk toolbar for the Trader 2x2 grid (Webull-style): draw tools act on
 * whichever pane is clicked next; indicator toggles act on the focused pane.
 * Replaces four per-pane toolbars that ate the chart height on small screens.
 */
import {
  CHART_DESK_TOOLBAR_ARIA,
  CHART_DESK_TOOLBAR_TARGET_TITLE,
  CHART_GRID_RESTORE_LABEL,
  CHART_GRID_RESTORE_TITLE,
  type ChartIndicatorId,
} from '../constants';
import { ChartToolbarControls } from './TickerChartControls';
import type { DrawingSelectionState } from '../chart/useChartDrawingManager';

interface Props {
  activeTool: string | null;
  focusedLabel: string;
  focusedIndicators: ChartIndicatorId[];
  showOptional: boolean;
  maximized: boolean;
  selection?: DrawingSelectionState | null;
  onToolClick: (toolId: string) => void;
  onClearAll: () => void;
  onColorChange?: (color: string) => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onToggleOptional: () => void;
  onRestore: () => void;
}

export function ChartGridToolbar({
  activeTool,
  focusedLabel,
  focusedIndicators,
  showOptional,
  maximized,
  selection = null,
  onToolClick,
  onClearAll,
  onColorChange,
  onIndicatorToggle,
  onToggleOptional,
  onRestore,
}: Props) {
  return (
    <div
      className="chart-toolbar chart-desk-toolbar"
      role="toolbar"
      aria-label={CHART_DESK_TOOLBAR_ARIA}
      data-testid="chart-desk-toolbar"
    >
      <div className="chart-desk-toolbar__scroll">
        <ChartToolbarControls
          activeTool={activeTool}
          enabledIndicators={focusedIndicators}
          selection={selection}
          onClearAll={onClearAll}
          onColorChange={onColorChange}
          onIndicatorToggle={onIndicatorToggle}
          onToolClick={onToolClick}
        />
        <span
          className="chart-desk-toolbar__target"
          title={CHART_DESK_TOOLBAR_TARGET_TITLE}
          data-testid="chart-desk-toolbar-target"
        >
          {focusedLabel}
        </span>
        <div className="chart-toolbar-spacer" />
        {maximized && (
          <button
            type="button"
            className="chart-grid__optional-toggle"
            onClick={onRestore}
            title={CHART_GRID_RESTORE_TITLE}
            aria-label={CHART_GRID_RESTORE_LABEL}
            data-testid="chart-grid-restore"
          >
            {CHART_GRID_RESTORE_LABEL}
          </button>
        )}
        <button
          type="button"
          className="chart-grid__optional-toggle"
          onClick={onToggleOptional}
          aria-pressed={showOptional}
          data-testid="chart-grid-optional-toggle"
        >
          {showOptional ? 'Hide 10-Second' : 'Show 10-Second'}
        </button>
      </div>
    </div>
  );
}
