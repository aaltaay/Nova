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
import type { ChartIndicatorId } from '../constants';
import { CHART_INDICATORS } from '../constants';
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
import {
  ChartContextSubmenu,
  ChartContextSubmenuRow,
} from './ChartContextSubmenu';
import type { ChartOrderIntent } from './chartOrderActions';

type SubmenuId = 'drawings' | 'show_layers';

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
  enabledIndicators: ChartIndicatorId[];
  onStageOrder: (intent: ChartOrderIntent) => void;
  onToolClick: (toolId: string) => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onViewDetails: () => void;
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
  const layersRowRef = useRef<HTMLButtonElement>(null);
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
  const [submenu, setSubmenu] = useState<SubmenuId | null>(null);
  const [submenuPos, setSubmenuPos] = useState({ top: 0, left: 0 });

  const items = chartContextMenuItems({
    symbol: props.symbol,
    price: props.price,
    quantityValue: props.quantityValue,
    hasPosition: Boolean(props.position && props.position.qty !== 0),
  });

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

  function openSubmenu(id: SubmenuId): void {
    const root = rootRef.current;
    const row = id === 'drawings' ? drawingsRowRef.current : layersRowRef.current;
    if (!root || !row) return;
    const view = viewport();
    const rootRect = root.getBoundingClientRect();
    const count = id === 'drawings' ? CHART_LINE_TOOLS.length : CHART_INDICATORS.length;
    setSubmenuPos(
      chartSubmenuPosition({
        parentLeft: rootRect.left,
        parentWidth: rootRect.width || CHART_CONTEXT_MENU_WIDTH_PX,
        rowTop: row.getBoundingClientRect().top,
        submenuWidth: CHART_CONTEXT_SUBMENU_WIDTH_PX,
        submenuHeight: count * 30,
        viewportWidth: view.width,
        viewportHeight: view.height,
      }),
    );
    setSubmenu(id);
  }

  function runItem(id: ChartContextMenuItemId): void {
    if (id === 'create_order' || id === 'buy' || id === 'sell') {
      props.onStageOrder(id);
    } else if (id === 'view_details') {
      props.onViewDetails();
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
      const id = item.id as SubmenuId;
      return (
        <ChartContextSubmenuRow
          key={item.id}
          testId={`chart-context-menu-${item.id}`}
          label={item.label}
          expanded={submenu === id}
          rowRef={id === 'drawings' ? drawingsRowRef : layersRowRef}
          onOpen={() => openSubmenu(id)}
          onToggle={() => (submenu === id ? setSubmenu(null) : openSubmenu(id))}
        />
      );
    }
    if (item.kind === 'unavailable') {
      return (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          className="chart-context-menu__item"
          data-testid={`chart-context-menu-${item.id}`}
          disabled
          title={item.reason}
          aria-disabled="true"
          onPointerEnter={() => setSubmenu(null)}
        >
          <span className="chart-context-menu__item-stack">
            <span>{item.label}</span>
            {item.reason ? (
              <span className="chart-context-menu__item-reason">{item.reason}</span>
            ) : null}
          </span>
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
        onPointerEnter={() => setSubmenu(null)}
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
      {submenu === 'drawings' && (
        <ChartContextSubmenu
          testId="chart-context-menu-drawings-submenu"
          ariaLabel="Drawings"
          top={submenuPos.top}
          left={submenuPos.left}
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
        </ChartContextSubmenu>
      )}
      {submenu === 'show_layers' && (
        <ChartContextSubmenu
          testId="chart-context-menu-layers-submenu"
          ariaLabel="Show Layers"
          top={submenuPos.top}
          left={submenuPos.left}
        >
          {CHART_INDICATORS.map((ind) => {
            const on = props.enabledIndicators.includes(ind.id);
            return (
              <button
                key={ind.id}
                type="button"
                role="menuitemcheckbox"
                aria-checked={on}
                className={
                  on
                    ? 'chart-context-menu__item chart-context-menu__item--active'
                    : 'chart-context-menu__item'
                }
                data-testid={`chart-context-menu-layer-${ind.id}`}
                onClick={() => props.onIndicatorToggle(ind.id)}
              >
                <span>{ind.label}</span>
                <span aria-hidden="true">{on ? '✓' : ''}</span>
              </button>
            );
          })}
        </ChartContextSubmenu>
      )}
    </div>
  );
}
