import {
  CHART_CARD_TITLE,
  CHART_INDICATORS,
  CHART_MOCK_DATA_LABEL,
  CHART_TIMEFRAMES,
  type ChartIndicatorId,
} from '../constants';
import { ChartDrawToolsMenu } from './ChartDrawToolsMenu';

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
  onClearAll: () => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onMaximize: () => void;
  onTimeframeChange: (timeframe: string) => void;
  onToolClick: (toolId: string) => void;
}

interface ToolbarProps {
  activeTool: string | null;
  enabledIndicators: ChartIndicatorId[];
  onClearAll: () => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onToolClick: (toolId: string) => void;
}

/** Draw tools + indicator toggles. Reused by the shared desk toolbar. */
export function ChartToolbarControls({
  activeTool,
  enabledIndicators,
  onClearAll,
  onIndicatorToggle,
  onToolClick,
}: ToolbarProps) {
  return (
    <>
      <ChartDrawToolsMenu activeTool={activeTool} onToolClick={onToolClick} />
      <button
        type="button"
        className={`chart-tool-btn${activeTool === 'CrossLine' ? ' chart-tool-btn--active' : ''}`}
        onClick={() => onToolClick('CrossLine')}
        title="Crosshair"
        aria-label="Use Crosshair"
      >
        <span className="chart-tool-icon">┼</span>
      </button>
      <button
        type="button"
        className="chart-tool-btn chart-tool-btn--danger"
        onClick={onClearAll}
        title="Clear all drawings. Delete or Backspace removes the selected line."
        aria-label="Clear all drawings"
      >
        <span className="chart-tool-icon">✕</span>
      </button>
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

function MaximizeButton({ maximized, onMaximize }: { maximized: boolean; onMaximize: () => void }) {
  return (
    <button
      type="button"
      className={`chart-tool-btn chart-maximize-btn${maximized ? ' chart-tool-btn--active' : ''}`}
      onClick={onMaximize}
      title={maximized ? 'Restore' : 'Maximize'}
      aria-label={maximized ? 'Restore chart' : 'Maximize chart'}
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
  onClearAll,
  onIndicatorToggle,
  onMaximize,
  onTimeframeChange,
  onToolClick,
}: Props) {
  // A maximized compact pane has no desk toolbar in view -- show its own.
  const showToolbar = !compact || maximized;
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
        {!showToolbar && <MaximizeButton maximized={maximized} onMaximize={onMaximize} />}
      </div>
      {showToolbar && (
        <div className="chart-toolbar">
          <ChartToolbarControls
            activeTool={activeTool}
            enabledIndicators={enabledIndicators}
            onClearAll={onClearAll}
            onIndicatorToggle={onIndicatorToggle}
            onToolClick={onToolClick}
          />
          <div className="chart-toolbar-spacer" />
          <MaximizeButton maximized={maximized} onMaximize={onMaximize} />
        </div>
      )}
    </>
  );
}
