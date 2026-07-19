import {
  CHART_CARD_TITLE,
  CHART_INDICATORS,
  CHART_MOCK_DATA_LABEL,
  CHART_SESSION_LEGEND,
  CHART_TIMEFRAMES,
  type ChartIndicatorId,
} from '../constants';

interface Props {
  activeTool: string | null;
  enabledIndicators: ChartIndicatorId[];
  lockTimeframe: boolean;
  maximized: boolean;
  showSessionLegend?: boolean;
  subtitle?: string;
  timeframe: string;
  title?: string;
  usingMock: boolean;
  onClearAll: () => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onMaximize: () => void;
  onTimeframeChange: (timeframe: string) => void;
  onToolClick: (toolId: string) => void;
}

const DRAW_TOOLS = [
  { id: 'TrendLine', label: 'Trend Line', icon: '╱' },
  { id: 'HorizontalLine', label: 'Horizontal Line', icon: '─' },
  { id: 'VerticalLine', label: 'Vertical Line', icon: '│' },
  { id: 'CrossLine', label: 'Crosshair', icon: '┼' },
];

export function TickerChartControls({
  activeTool,
  enabledIndicators = [],
  lockTimeframe,
  maximized,
  showSessionLegend = false,
  subtitle,
  timeframe,
  title,
  usingMock,
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
        {showSessionLegend && (
          <div
            className="chart-session-legend"
            title="Background: premarket 04:00–09:30 · RTH 09:30–16:00 · after-hours 16:00–20:00 ET"
            aria-label="Session background legend"
          >
            {CHART_SESSION_LEGEND.map(item => (
              <span key={item.id} className="chart-session-legend-item">
                <span
                  className="chart-session-swatch"
                  style={{ background: item.color }}
                  aria-hidden="true"
                />
                {item.label}
              </span>
            ))}
          </div>
        )}
        {usingMock && <span className="chart-mock-badge" title={CHART_MOCK_DATA_LABEL}>{CHART_MOCK_DATA_LABEL}</span>}
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
        {DRAW_TOOLS.map(tool => (
          <button
            key={tool.id}
            className={`chart-tool-btn${activeTool === tool.id ? ' chart-tool-btn--active' : ''}`}
            onClick={() => onToolClick(tool.id)}
            title={tool.label}
          >
            <span className="chart-tool-icon">{tool.icon}</span>
          </button>
        ))}
        <button
          className="chart-tool-btn chart-tool-btn--danger"
          onClick={onClearAll}
          title="Clear all drawings"
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
