import { CHART_CARD_TITLE, CHART_MOCK_DATA_LABEL, CHART_TIMEFRAMES } from '../constants';

interface Props {
  activeTool: string | null;
  lockTimeframe: boolean;
  maximized: boolean;
  subtitle?: string;
  timeframe: string;
  title?: string;
  usingMock: boolean;
  onClearAll: () => void;
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
  lockTimeframe,
  maximized,
  subtitle,
  timeframe,
  title,
  usingMock,
  onClearAll,
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
