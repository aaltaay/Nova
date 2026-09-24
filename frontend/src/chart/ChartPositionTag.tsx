/**
 * Clickable Long/Short badge + Webull-style in-app menu.
 * Left-click / right-click open the menu. Esc and outside click dismiss.
 * Pointer events stop here so chart draw / pan do not start.
 */
import {
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type PointerEvent,
  type RefObject,
} from 'react';
import { ClosePositionButton } from '../closed_orders';
import type { IbkrMode, IbkrPosition } from '../ibkr/types';
import { requestStockViewDock } from '../stock_view/requestDockSurface';
import { positionLineTitle } from './positionOverlay';
import { useChartPositionContext } from './useChartPositionContext';
import {
  CHART_POSITION_LONG_COLOR,
  CHART_POSITION_MENU_CLOSE,
  CHART_POSITION_MENU_LABEL,
  CHART_POSITION_MENU_VIEW_DETAILS,
  CHART_POSITION_SHORT_COLOR,
  CHART_POSITION_TAG_LABEL,
} from './positionOverlayConstants';
import { chartPositionMenuItems } from './positionMenu';
import { useChartPositionTagLayout } from './useChartPositionTagLayout';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

function haltChartGesture(e: PointerEvent | MouseEvent): void {
  e.preventDefault();
  e.stopPropagation();
}

function snapshotFromRow(row: IbkrPosition) {
  return {
    symbol: (row.symbol || '').toUpperCase(),
    qty: row.qty,
    avgCost: row.avg_cost ?? 0,
    unrealizedPnl: row.unrealized_pnl,
  };
}

export function ChartPositionMenu(props: {
  position: IbkrPosition;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  flattenDisabled?: boolean;
  /** Why `flattenDisabled` is set (ux/whyTip.ts). */
  flattenWhy?: string | null;
  onViewDetails: () => void;
  onClosed?: () => void;
}) {
  const items = chartPositionMenuItems();
  return (
    <div
      className="chart-position-menu"
      role="menu"
      aria-label={CHART_POSITION_MENU_LABEL}
      data-testid="chart-position-menu"
      onPointerDown={haltChartGesture}
      onPointerUp={haltChartGesture}
      onClick={haltChartGesture}
      onContextMenu={haltChartGesture}
    >
      {items.map((item) =>
        item.id === 'close' ? (
          <ClosePositionButton
            key={item.id}
            position={props.position}
            mode={props.mode}
            connected={props.connected}
            spendStatus={props.spendStatus}
            disabled={props.flattenDisabled}
            why={props.flattenWhy}
            variant="menu"
            label={CHART_POSITION_MENU_CLOSE}
            testId="chart-position-menu-close"
            onClosed={props.onClosed}
          />
        ) : (
          <button
            key={item.id}
            type="button"
            role="menuitem"
            className="chart-position-menu__item"
            data-testid="chart-position-menu-details"
            onClick={() => props.onViewDetails()}
          >
            {CHART_POSITION_MENU_VIEW_DETAILS}
          </button>
        ),
      )}
    </div>
  );
}

export function ChartPositionTag(props: {
  position: IbkrPosition;
  placement: { top: number; right: number };
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  flattenDisabled?: boolean;
  flattenWhy?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const short = props.position.qty < 0;
  const title = positionLineTitle(snapshotFromRow(props.position));

  function openMenu(e: PointerEvent | MouseEvent): void {
    haltChartGesture(e);
    setOpen(true);
  }

  useEffect(() => {
    if (!open) return;
    const onDown = (e: globalThis.PointerEvent) => {
      const root = rootRef.current;
      if (root && root.contains(e.target as Node)) return;
      e.stopPropagation();
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopImmediatePropagation();
      setOpen(false);
    };
    document.addEventListener('pointerdown', onDown, true);
    window.addEventListener('keydown', onKey, true);
    return () => {
      document.removeEventListener('pointerdown', onDown, true);
      window.removeEventListener('keydown', onKey, true);
    };
  }, [open]);

  return (
    <div
      ref={rootRef}
      className="chart-position-tag"
      style={{ top: props.placement.top, right: props.placement.right }}
      data-testid="chart-position-tag"
    >
      <button
        type="button"
        className={
          short
            ? 'chart-position-tag__badge chart-position-tag__badge--short'
            : 'chart-position-tag__badge'
        }
        style={{
          background: short ? CHART_POSITION_SHORT_COLOR : CHART_POSITION_LONG_COLOR,
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${CHART_POSITION_TAG_LABEL}: ${title}`}
        data-testid="chart-position-tag-btn"
        onPointerDown={openMenu}
        onPointerUp={haltChartGesture}
        onClick={haltChartGesture}
        onContextMenu={openMenu}
      >
        {title}
      </button>
      {open ? (
        <ChartPositionMenu
          position={props.position}
          mode={props.mode}
          connected={props.connected}
          spendStatus={props.spendStatus}
          flattenDisabled={props.flattenDisabled}
          flattenWhy={props.flattenWhy}
          onViewDetails={() => {
            setOpen(false);
            requestStockViewDock({ surface: 'positions' });
          }}
          onClosed={() => setOpen(false)}
        />
      ) : null}
    </div>
  );
}

export function ChartPositionTagHost(props: {
  symbol: string;
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  barsRevision: number;
}) {
  const ctx = useChartPositionContext(props.symbol);
  const row = ctx.position;
  const placement = useChartPositionTagLayout({
    chart: props.chart,
    candleSeriesRef: props.candleSeriesRef,
    containerRef: props.containerRef,
    avgCost: row?.avg_cost ?? 0,
    barsRevision: props.barsRevision,
  });
  if (!row) return null;
  return (
    <ChartPositionTag
      position={row}
      placement={placement}
      mode={ctx.mode}
      connected={ctx.connected}
      spendStatus={ctx.spendStatus}
      flattenDisabled={ctx.flattenDisabled}
      flattenWhy={ctx.flattenWhy}
    />
  );
}
