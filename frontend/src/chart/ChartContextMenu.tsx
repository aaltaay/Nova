/**
 * Webull-style chart right-click menu (view only).
 *
 * Money rows delegate: order rows call `onStageOrder` (ticket prefill) and
 * Close Position renders the shared `ClosePositionButton`, the same component
 * the Positions table and the Long/Short tag menu use. This file must never
 * grow its own place/flatten call.
 */
import { useLayoutEffect, useRef, useState, type MouseEvent } from 'react';
import { ClosePositionButton } from '../closed_orders';
import type { IbkrMode, IbkrPosition } from '../ibkr/types';
import { CHART_LINE_TOOLS } from './chartDrawingConfig';
import {
  CHART_CONTEXT_MENU_EST_HEIGHT_PX,
  CHART_CONTEXT_MENU_LABEL,
  CHART_CONTEXT_MENU_ORDER_HINT,
  CHART_CONTEXT_MENU_WIDTH_PX,
  CHART_CONTEXT_SUBMENU_WIDTH_PX,
} from './chartContextMenuConstants';
import {
  chartContextMenuItems,
  type ChartContextMenuItem,
  type ChartContextMenuItemId,
} from './chartContextMenuItems';
import {
  chartContextMenuPosition,
  chartSubmenuPosition,
} from './chartContextMenuPosition';
import type { ChartOrderIntent } from './chartOrderActions';

export interface ChartContextMenuProps {
  symbol: string;
  price: number | null;
  quantityValue: string;
  anchor: { x: number; y: number };
  position: IbkrPosition | null;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  flattenDisabled?: boolean;
  activeTool: string | null;
  onStageOrder: (intent: ChartOrderIntent) => void;
  onToolClick: (toolId: string) => void;
  onReset: () => void;
  onSnapshot: () => void;
  onDismiss: () => void;
}

function viewport(): { width: number; height: number } {
  if (typeof window === 'undefined') return { width: 1280, height: 800 };
  return { width: window.innerWidth, height: window.innerHeight };
}

export function ChartContextMenu(props: ChartContextMenuProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const drawingsRowRef = useRef<HTMLButtonElement>(null);
  const [placement, setPlacement] = useState(() => {
    const view = viewport();
    return chartContextMenuPosition({
      x: props.anchor.x,
      y: props.anchor.y,
      menuWidth: CHART_CONTEXT_MENU_WIDTH_PX,
      menuHeight: CHART_CONTEXT_MENU_EST_HEIGHT_PX,
      viewportWidth: view.width,
      viewportHeight: view.height,
    });
  });
  const [submenuOpen, setSubmenuOpen] = useState(false);
  const [submenuPos, setSubmenuPos] = useState({ top: 0, left: 0 });

  const items = chartContextMenuItems({
    symbol: props.symbol,
    price: props.price,
    quantityValue: props.quantityValue,
    hasPosition: Boolean(props.position && props.position.qty !== 0),
  });

  // Re-place once the real height is known (order rows are conditional).
  useLayoutEffect(() => {
    const node = rootRef.current;
    if (!node) return;
    const view = viewport();
    const rect = node.getBoundingClientRect();
    setPlacement(
      chartContextMenuPosition({
        x: props.anchor.x,
        y: props.anchor.y,
        menuWidth: rect.width || CHART_CONTEXT_MENU_WIDTH_PX,
        menuHeight: rect.height || CHART_CONTEXT_MENU_EST_HEIGHT_PX,
        viewportWidth: view.width,
        viewportHeight: view.height,
      }),
    );
  }, [props.anchor.x, props.anchor.y, items.length]);

  function openSubmenu(): void {
    const root = rootRef.current;
    const row = drawingsRowRef.current;
    if (!root || !row) return;
    const view = viewport();
    const rootRect = root.getBoundingClientRect();
    setSubmenuPos(
      chartSubmenuPosition({
        parentLeft: rootRect.left,
        parentWidth: rootRect.width || CHART_CONTEXT_MENU_WIDTH_PX,
        rowTop: row.getBoundingClientRect().top,
        submenuWidth: CHART_CONTEXT_SUBMENU_WIDTH_PX,
        submenuHeight: CHART_LINE_TOOLS.length * 30,
        viewportWidth: view.width,
        viewportHeight: view.height,
      }),
    );
    setSubmenuOpen(true);
  }

  function runItem(id: ChartContextMenuItemId): void {
    if (id === 'create_order' || id === 'buy' || id === 'sell') {
      props.onStageOrder(id);
    } else if (id === 'reset') {
      props.onReset();
    } else if (id === 'snapshot') {
      props.onSnapshot();
    }
    props.onDismiss();
  }

  function renderItem(item: ChartContextMenuItem) {
    if (item.kind === 'position' && props.position) {
      return (
        <ClosePositionButton
          key={item.id}
          position={props.position}
          mode={props.mode}
          connected={props.connected}
          spendStatus={props.spendStatus}
          disabled={props.flattenDisabled}
          variant="menu"
          label={item.label}
          testId="chart-context-menu-close-position"
          onClosed={props.onDismiss}
        />
      );
    }
    if (item.kind === 'submenu') {
      return (
        <button
          key={item.id}
          ref={drawingsRowRef}
          type="button"
          role="menuitem"
          className="chart-context-menu__item chart-context-menu__item--submenu"
          aria-haspopup="menu"
          aria-expanded={submenuOpen}
          data-testid="chart-context-menu-drawings"
          onPointerEnter={openSubmenu}
          onClick={() => (submenuOpen ? setSubmenuOpen(false) : openSubmenu())}
        >
          <span>{item.label}</span>
          <span aria-hidden="true" className="chart-context-menu__caret">›</span>
        </button>
      );
    }
    return (
      <button
        key={item.id}
        type="button"
        role="menuitem"
        className="chart-context-menu__item"
        data-testid={`chart-context-menu-${item.id}`}
        onPointerEnter={() => setSubmenuOpen(false)}
        onClick={() => runItem(item.id)}
      >
        {item.label}
      </button>
    );
  }

  const hasOrderRows = items.some((item) => item.kind === 'order');

  return (
    <div
      ref={rootRef}
      className="chart-context-menu"
      role="menu"
      aria-label={CHART_CONTEXT_MENU_LABEL}
      data-testid="chart-context-menu"
      style={{ top: placement.top, left: placement.left }}
      onContextMenu={(e: MouseEvent) => e.preventDefault()}
    >
      {items.map((item) => (
        <div
          key={item.id}
          className={
            item.dividerBefore
              ? 'chart-context-menu__row chart-context-menu__row--divider'
              : 'chart-context-menu__row'
          }
        >
          {renderItem(item)}
        </div>
      ))}
      {hasOrderRows && (
        <p className="chart-context-menu__hint" data-testid="chart-context-menu-hint">
          {CHART_CONTEXT_MENU_ORDER_HINT}
        </p>
      )}
      {submenuOpen && (
        <div
          className="chart-context-menu chart-context-menu--submenu"
          role="menu"
          aria-label="Drawings"
          data-testid="chart-context-menu-drawings-submenu"
          style={{ top: submenuPos.top, left: submenuPos.left }}
        >
          {CHART_LINE_TOOLS.map((tool) => (
            <button
              key={tool.id}
              type="button"
              role="menuitemradio"
              aria-checked={props.activeTool === tool.id}
              className={
                props.activeTool === tool.id
                  ? 'chart-context-menu__item chart-context-menu__item--active'
                  : 'chart-context-menu__item'
              }
              data-testid={`chart-context-menu-tool-${tool.id}`}
              onClick={() => {
                props.onToolClick(tool.id);
                props.onDismiss();
              }}
            >
              <span>{tool.label}</span>
              <kbd>{tool.hotkey}</kbd>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
