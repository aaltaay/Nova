/**
 * One desk toolbar for the Trader 2x2 grid (Webull-style): draw tools act on
 * whichever pane is clicked next; indicator toggles act on the focused pane.
 * Replaces four per-pane toolbars that ate the chart height on small screens.
 */
import {
  CHART_DESK_TOOLBAR_ARIA,
  CHART_DESK_TOOLBAR_TARGET_TITLE,
  type ChartIndicatorId,
} from '../constants';
import { ChartToolbarControls } from './TickerChartControls';

interface Props {
  activeTool: string | null;
  focusedLabel: string;
  focusedIndicators: ChartIndicatorId[];
  showOptional: boolean;
  onToolClick: (toolId: string) => void;
  onClearAll: () => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onToggleOptional: () => void;
}

export function ChartGridToolbar({
  activeTool,
  focusedLabel,
  focusedIndicators,
  showOptional,
  onToolClick,
  onClearAll,
  onIndicatorToggle,
  onToggleOptional,
}: Props) {
  return (
    <div
      className="chart-toolbar chart-desk-toolbar"
      role="toolbar"
      aria-label={CHART_DESK_TOOLBAR_ARIA}
      data-testid="chart-desk-toolbar"
    >
      <ChartToolbarControls
        activeTool={activeTool}
        enabledIndicators={focusedIndicators}
        onClearAll={onClearAll}
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
  );
}
