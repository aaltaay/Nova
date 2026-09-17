import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  CHART_DRAW_TOOLS_MENU_Z_INDEX,
  type ChartDrawToolsLayout,
  chartDrawToolsMenuPortalTarget,
} from '../chart/chartDrawToolsChrome';
import { CHART_LINE_TOOLS } from '../chart/chartDrawingConfig';

interface Props {
  activeTool: string | null;
  onToolClick: (toolId: string) => void;
  /** Maximized chrome uses `flat`; compact toolbars keep the cluster. */
  layout?: ChartDrawToolsLayout;
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

const MENU_GAP_PX = 5;

export function chartDrawToolsMenuPosition(rect: { bottom: number; left: number }): {
  top: number;
  left: number;
} {
  return { top: rect.bottom + MENU_GAP_PX, left: rect.left };
}

function ChartDrawToolsBar({ activeTool, onToolClick }: Props) {
  return (
    <div
      className="chart-draw-tools chart-draw-tools--flat"
      role="group"
      aria-label="Line drawing tools"
      data-testid="chart-draw-tools-flat"
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

export function ChartDrawToolsMenu({
  activeTool,
  onToolClick,
  layout = 'cluster',
}: Props) {
  if (layout === 'flat') {
    return <ChartDrawToolsBar activeTool={activeTool} onToolClick={onToolClick} />;
  }
  return <ChartDrawToolsCluster activeTool={activeTool} onToolClick={onToolClick} />;
}

function ChartDrawToolsCluster({ activeTool, onToolClick }: Props) {
  const [open, setOpen] = useState(false);
  const [lastUsedId, setLastUsedId] = useState(CHART_LINE_TOOLS[0].id);
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 });
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const lastUsed = CHART_LINE_TOOLS.find((tool) => tool.id === lastUsedId)
    ?? CHART_LINE_TOOLS[0];

  useEffect(() => {
    if (activeTool && CHART_LINE_TOOLS.some((tool) => tool.id === activeTool)) {
      setLastUsedId(activeTool);
    }
  }, [activeTool]);

  useLayoutEffect(() => {
    if (!open || !rootRef.current) return;
    const sync = () => {
      if (!rootRef.current) return;
      setMenuPos(chartDrawToolsMenuPosition(rootRef.current.getBoundingClientRect()));
    };
    sync();
    window.addEventListener('resize', sync);
    window.addEventListener('scroll', sync, true);
    return () => {
      window.removeEventListener('resize', sync);
      window.removeEventListener('scroll', sync, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', closeOnOutsidePointer);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const chooseTool = (toolId: string) => {
    setLastUsedId(toolId);
    setOpen(false);
    onToolClick(toolId);
  };

  const menu = open
    ? createPortal(
      <div
        ref={menuRef}
        className="chart-draw-tools__menu"
        role="menu"
        aria-label="Line drawing tools"
        data-testid="chart-draw-tools-menu"
        style={{
          top: menuPos.top,
          left: menuPos.left,
          zIndex: CHART_DRAW_TOOLS_MENU_Z_INDEX,
        }}
      >
        {CHART_LINE_TOOLS.map((tool) => (
          <button
            type="button"
            role="menuitemradio"
            aria-checked={activeTool === tool.id}
            className={`chart-draw-tools__item${activeTool === tool.id ? ' chart-draw-tools__item--active' : ''}`}
            key={tool.id}
            onClick={() => chooseTool(tool.id)}
          >
            <ToolIcon toolId={tool.id} />
            <span className="chart-draw-tools__label">{tool.label}</span>
            <kbd>{tool.hotkey}</kbd>
          </button>
        ))}
      </div>,
      chartDrawToolsMenuPortalTarget(),
    )
    : null;

  return (
    <div className="chart-draw-tools" ref={rootRef}>
      <button
        type="button"
        className={`chart-tool-btn chart-draw-tools__main${activeTool === lastUsed.id ? ' chart-tool-btn--active' : ''}`}
        onClick={() => onToolClick(lastUsed.id)}
        aria-label={`Use ${lastUsed.label}`}
        title={`${lastUsed.label} (${lastUsed.hotkey})`}
      >
        <ToolIcon toolId={lastUsed.id} />
      </button>
      <button
        type="button"
        className={`chart-tool-btn chart-draw-tools__toggle${open ? ' chart-tool-btn--active' : ''}`}
        onClick={() => setOpen((current) => !current)}
        aria-label="Line drawing tools"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Line drawing tools"
      >
        <span aria-hidden="true">▾</span>
      </button>
      {menu}
    </div>
  );
}
