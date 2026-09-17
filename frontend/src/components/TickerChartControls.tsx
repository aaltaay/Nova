import { chartDrawToolsLayout } from '../chart/chartDrawToolsChrome';
import {
  CHART_CARD_TITLE,
  CHART_FULLSCREEN_ARIA,
  CHART_FULLSCREEN_RESTORE_ARIA,
  CHART_FULLSCREEN_RESTORE_TITLE,
  CHART_FULLSCREEN_TITLE,
  CHART_INDICATORS,
  CHART_MOCK_DATA_LABEL,
  CHART_TIMEFRAMES,
  type ChartIndicatorId,
} from '../constants';
import { ChartDrawToolsMenu } from './ChartDrawToolsMenu';
import { ChartDrawingColorPicker } from './ChartDrawingColorPicker';
import type { DrawingSelectionState } from '../chart/useChartDrawingManager';

interface Props {
  activeTool: string | null;
  enabledIndicators: ChartIndicatorId[];
  lockTimeframe: boolean;
  maximized: boolean;
  subtitle?: string;
  timeframe: string;
  title?: string;
  usingMock: boolean;
  /** Store-first fill status -- lives in the header so it cannot cover the time axis. */
  fillingHint?: string | null;
  /**
   * Trader grid: one header line, no per-pane toolbar. The shared desk toolbar
   * above the grid owns draw tools + indicator toggles for the focused pane.
   */
  compact?: boolean;
  /**
   * Grid-local maximize keeps the desk toolbar in view, so compact chrome
   * stays one header line (do not grow a second per-pane toolbar).
   */
  keepCompactWhenMaximized?: boolean;
  /** Header uses the Fullscreen API (Trader grid). */
  useFullscreenExpand?: boolean;
  maximizeTitle?: string;
  restoreTitle?: string;
  selection?: DrawingSelectionState | null;
  onClearAll: () => void;
  onColorChange?: (color: string) => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onMaximize: () => void;
  onTimeframeChange: (timeframe: string) => void;
  onToolClick: (toolId: string) => void;
}

interface ToolbarProps {
  activeTool: string | null;
  enabledIndicators: ChartIndicatorId[];
  selection?: DrawingSelectionState | null;
  /** When true, line tools render as individual buttons (maximized chrome). */
  maximized?: boolean;
  onClearAll: () => void;
  onColorChange?: (color: string) => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onToolClick: (toolId: string) => void;
}

/** Draw tools + indicator toggles. Reused by the shared desk toolbar. */
export function ChartToolbarControls({
  activeTool,
  enabledIndicators,
  selection = null,
  maximized = false,
  onClearAll,
  onColorChange,
  onIndicatorToggle,
  onToolClick,
}: ToolbarProps) {
  return (
    <>
      <ChartDrawToolsMenu
        activeTool={activeTool}
        onToolClick={onToolClick}
        layout={chartDrawToolsLayout(maximized)}
      />
      <button
        type="button"
        className={`chart-tool-btn${activeTool === 'CrossLine' ? ' chart-tool-btn--active' : ''}`}
        onClick={() => onToolClick('CrossLine')}
        title="Crosshair"
        aria-label="Use Crosshair"
      >
        <span className="chart-tool-icon">&#x253C;</span>
      </button>
      <button
        type="button"
        className="chart-tool-btn chart-tool-btn--danger"
        onClick={onClearAll}
        title="Clear all drawings. Delete or Backspace removes the selected line."
        aria-label="Clear all drawings"
      >
        <span className="chart-tool-icon">&#x2715;</span>
      </button>
      {selection && onColorChange && (
        <>
          <div className="chart-toolbar-divider" aria-hidden="true" />
          <ChartDrawingColorPicker
            currentColor={selection.color}
            onColorChange={onColorChange}
          />
        </>
      )}
      <div className="chart-toolbar-divider" aria-hidden="true" />
      <div className="chart-tabs" role="group" aria-label="Indicators">
        {CHART_INDICATORS.map(ind => (
          <button
            key={ind.id}
            className={`chart-tab${enabledIndicators.includes(ind.id) ? ' chart-tab--active' : ''}`}
            onClick={() => onIndicatorToggle(ind.id)}
            aria-pressed={enabledIndicators.includes(ind.id)}
            title={`${ind.label} (from lightweight-charts-indicators)`}
          >
            {ind.label}
          </button>
        ))}
      </div>
    </>
  );
}

function MaximizeButton({
  maximized,
  onMaximize,
  maximizeTitle = 'Maximize',
  restoreTitle = 'Restore',
  maximizeAria = 'Maximize chart',
  restoreAria = 'Restore chart',
}: {
  maximized: boolean;
  onMaximize: () => void;
  maximizeTitle?: string;
  restoreTitle?: string;
  maximizeAria?: string;
  restoreAria?: string;
}) {
  return (
    <button
      type="button"
      className={`chart-tool-btn chart-maximize-btn${maximized ? ' chart-tool-btn--active' : ''}`}
      onClick={onMaximize}
      title={maximized ? restoreTitle : maximizeTitle}
      aria-label={maximized ? restoreAria : maximizeAria}
      data-testid="chart-expand-btn"
    >
      <span className="chart-tool-icon">{maximized ? '⊙' : '⛶'}</span>
    </button>
  );
}

export function TickerChartControls({
  activeTool,
  enabledIndicators = [],
  lockTimeframe,
  maximized,
  subtitle,
  timeframe,
  title,
  usingMock,
  fillingHint = null,
  compact = false,
  keepCompactWhenMaximized = false,
  useFullscreenExpand = false,
  maximizeTitle,
  restoreTitle,
  selection = null,
  onClearAll,
  onColorChange,
  onIndicatorToggle,
  onMaximize,
  onTimeframeChange,
  onToolClick,
}: Props) {
  // Viewport maximize covers the desk toolbar, so a compact pane grows one.
  // Grid-local maximize keeps that toolbar, so chrome stays one header line.
  const showToolbar = !compact || (maximized && !keepCompactWhenMaximized);
  const useFullscreenCopy = useFullscreenExpand;
  const maxTitle =
    maximizeTitle ?? (useFullscreenCopy ? CHART_FULLSCREEN_TITLE : 'Maximize');
  const rstTitle =
    restoreTitle ?? (useFullscreenCopy ? CHART_FULLSCREEN_RESTORE_TITLE : 'Restore');
  const maxBtn = (
    <MaximizeButton
      maximized={maximized}
      onMaximize={onMaximize}
      maximizeTitle={maxTitle}
      restoreTitle={rstTitle}
      maximizeAria={useFullscreenCopy ? CHART_FULLSCREEN_ARIA : 'Maximize chart'}
      restoreAria={useFullscreenCopy ? CHART_FULLSCREEN_RESTORE_ARIA : 'Restore chart'}
    />
  );
  return (
    <>
      <div className={`chart-header${compact ? ' chart-header--compact' : ''}`}>
        <div className="chart-title-block">
          <span className="chart-title">{title ?? CHART_CARD_TITLE}</span>
          {subtitle && <span className="chart-subtitle" title={subtitle}>{subtitle}</span>}
        </div>
        {usingMock && <span className="chart-mock-badge" title={CHART_MOCK_DATA_LABEL}>{CHART_MOCK_DATA_LABEL}</span>}
        {fillingHint && (
          <span className="chart-filling-hint" role="status">{fillingHint}</span>
        )}
        {!lockTimeframe ? (
          <div className="chart-tabs" role="group" aria-label="Timeframe">
            {CHART_TIMEFRAMES.map(option => (
              <button
                key={option.id}
                className={`chart-tab${timeframe === option.id ? ' chart-tab--active' : ''}`}
                onClick={() => onTimeframeChange(option.id)}
                aria-pressed={timeframe === option.id}
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : (
          <span className="chart-tf-badge" aria-label={`Timeframe ${timeframe}`}>{timeframe}</span>
        )}
        {!showToolbar && maxBtn}
      </div>
      {showToolbar && (
        <div className="chart-toolbar">
          <ChartToolbarControls
            activeTool={activeTool}
            enabledIndicators={enabledIndicators}
            selection={selection}
            maximized={maximized}
            onClearAll={onClearAll}
            onColorChange={onColorChange}
            onIndicatorToggle={onIndicatorToggle}
            onToolClick={onToolClick}
          />
          <div className="chart-toolbar-spacer" />
          {maxBtn}
        </div>
      )}
    </>
  );
}
