/**
 * The six line tools, each its own toolbar button (operator ask, 2026-09-24:
 * "there is no reason to have this dropdown menu ... we have enough space").
 * The toolbar wraps when a column is too narrow to hold them on one row.
 */
import { CHART_LINE_TOOLS } from '../chart/chartDrawingConfig';

interface Props {
  activeTool: string | null;
  onToolClick: (toolId: string) => void;
}

function ChartLineToolIcon({ toolId }: { toolId: string }) {
  if (toolId === 'HorizontalLine') {
    return <line x1="2" y1="10" x2="18" y2="10" />;
  }
  if (toolId === 'VerticalLine') {
    return <line x1="10" y1="2" x2="10" y2="18" />;
  }
  if (toolId === 'ExtendedLine') {
    return <line x1="0" y1="18" x2="20" y2="2" />;
  }
  if (toolId === 'Ray') {
    return (
      <>
        <circle cx="4" cy="16" r="1.5" />
        <line x1="4" y1="16" x2="20" y2="2" />
      </>
    );
  }
  if (toolId === 'HorizontalRay') {
    return (
      <>
        <circle cx="4" cy="10" r="1.5" />
        <line x1="4" y1="10" x2="20" y2="10" />
      </>
    );
  }
  return (
    <>
      <circle cx="3" cy="17" r="1.25" />
      <line x1="3" y1="17" x2="17" y2="3" />
      <circle cx="17" cy="3" r="1.25" />
    </>
  );
}

function ToolIcon({ toolId }: { toolId: string }) {
  return (
    <svg
      className="chart-line-tool-icon"
      viewBox="0 0 20 20"
      aria-hidden="true"
      focusable="false"
    >
      <ChartLineToolIcon toolId={toolId} />
    </svg>
  );
}

export function ChartDrawTools({ activeTool, onToolClick }: Props) {
  return (
    <div
      className="chart-draw-tools"
      role="group"
      aria-label="Line drawing tools"
      data-testid="chart-draw-tools"
    >
      {CHART_LINE_TOOLS.map((tool) => (
        <button
          type="button"
          key={tool.id}
          className={`chart-tool-btn${activeTool === tool.id ? ' chart-tool-btn--active' : ''}`}
          onClick={() => onToolClick(tool.id)}
          aria-label={`Use ${tool.label}`}
          aria-pressed={activeTool === tool.id}
          title={`${tool.label} (${tool.hotkey})`}
        >
          <ToolIcon toolId={tool.id} />
        </button>
      ))}
    </div>
  );
}
