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
  onClearAll: () => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onMaximize: () => void;
  onTimeframeChange: (timeframe: string) => void;
  onToolClick: (toolId: string) => void;
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
  onClearAll,
  onIndicatorToggle,
  onMaximize,
  onTimeframeChange,
  onToolClick,
}: Props) {
  return (
    <>
      <div className="chart-header">
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
      </div>
      <div className="chart-toolbar">
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
        <div className="chart-toolbar-spacer" />
        <button
          className={`chart-tool-btn${maximized ? ' chart-tool-btn--active' : ''}`}
          onClick={onMaximize}
          title={maximized ? 'Restore' : 'Maximize'}
        >
          <span className="chart-tool-icon">{maximized ? '⊙' : '⛶'}</span>
        </button>
      </div>
    </>
  );
}
