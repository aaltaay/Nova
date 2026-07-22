/** Collapsible Stock View Positions / Orders / Nova OS strip (WID-019 / 026 / 027). */
import { useEffect, useMemo, useState } from 'react';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import {
  ORDERS_TODAY_TITLE,
  STOCK_VIEW_MODULE_NOVA_OS_TITLE,
  STOCK_VIEW_MODULE_POSITIONS_TITLE,
  STOCK_VIEW_OPEN_ORDERS_SAMPLE_BANNER,
  STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY,
  type StockViewDockSurface,
} from '../constants';
import { PositionsPanel } from '../ibkr/PositionsPanel';
import { buildMockWorkingOrders } from '../ibkr/mockWorkingOrders';
import type {
  IbkrAccountSummary,
  IbkrMode,
  IbkrOrder,
  IbkrPosition,
} from '../ibkr/types';
import { OrdersTodayView, ordersTodayBadgeCount } from '../orders_today';
import type { OrdersTodayFilter } from '../orders_today';
import {
  readCollapsed,
  readFilter,
  readSampleHidden,
  readSurface,
  writeCollapsed,
  writeFilter,
  writeSurface,
} from './stockViewDockPersist';
import { TraderNovaOsBrain } from './TraderNovaOsBrain';

type Props = {
  symbol: string;
  orders: IbkrOrder[];
  positions: IbkrPosition[];
  symbolPosition?: IbkrPosition | null;
  summary: IbkrAccountSummary | null;
  /** useIbkrAccount poll failure — disables Flatten on last-good rows. */
  accountError?: string | null;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  onSelectSymbol: (symbol: string) => void;
  onCancelOrder?: (id: number) => void;
  onFillImmediately?: (order: IbkrOrder) => void;
  onPositionClosed?: () => void;
  highlightOrderId?: number | null;
  onCollapsedChange?: (collapsed: boolean) => void;
};

export function StockViewOpenOrdersDock({
  symbol,
  orders,
  positions,
  symbolPosition = null,
  summary,
  accountError = null,
  mode,
  connected,
  spendStatus,
  onSelectSymbol,
  onCancelOrder,
  onFillImmediately,
  onPositionClosed,
  highlightOrderId = null,
  onCollapsedChange,
}: Props) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [sampleHidden, setSampleHidden] = useState(readSampleHidden);
  const [filter, setFilter] = useState<OrdersTodayFilter>(readFilter);
  const [surface, setSurface] = useState<StockViewDockSurface>(readSurface);

  useEffect(() => {
    onCollapsedChange?.(collapsed);
  }, [collapsed, onCollapsedChange]);

  const { orders: closedOrders } = useClosedOrders(connected);

  const symbolKey = symbol.toUpperCase();
  const symbolOrders = useMemo(
    () => orders.filter((o) => o.symbol.toUpperCase() === symbolKey),
    [orders, symbolKey],
  );
  const wantsWorkingSample =
    surface === 'orders' &&
    (filter === 'working' || filter === 'all' || filter === 'partial_filled');
  const usingSample =
    wantsWorkingSample && symbolOrders.length === 0 && !sampleHidden;
  const displayOrders = useMemo(
    () => (usingSample ? buildMockWorkingOrders(symbolKey) : orders),
    [usingSample, symbolKey, orders],
  );
  // Real closed only (never sample) — see ordersTodayBadgeCount.
  const openCount = ordersTodayBadgeCount(
    displayOrders,
    closedOrders,
    filter,
    symbolKey,
  );
  const positionCount = positions.length;

  useEffect(() => {
    if (
      highlightOrderId != null ||
      symbolOrders.length > 0 ||
      usingSample ||
      positions.length > 0
    ) {
      setCollapsed(false);
      writeCollapsed(false);
    }
  }, [highlightOrderId, symbolOrders.length, usingSample, positions.length]);

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  };

  const selectFilter = (next: OrdersTodayFilter) => {
    setFilter(next);
    writeFilter(next);
    setCollapsed(false);
    writeCollapsed(false);
  };

  const selectSurface = (next: StockViewDockSurface) => {
    setSurface(next);
    writeSurface(next);
    setCollapsed(false);
    writeCollapsed(false);
  };

  const hideSample = () => {
    setSampleHidden(true);
    try {
      localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, '1');
    } catch {
      /* ignore */
    }
  };

  const showSample = () => {
    setSampleHidden(false);
    try {
      localStorage.removeItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY);
    } catch {
      /* ignore */
    }
    setCollapsed(false);
    writeCollapsed(false);
  };

  return (
    <section
      className={`sv-open-orders-dock${collapsed ? ' sv-open-orders-dock--collapsed' : ''}${
        usingSample ? ' sv-open-orders-dock--sample' : ''
      }`}
      data-testid="stock-view-open-orders-dock"
      data-dock-surface={surface}
      data-orders-filter={filter}
      data-sample={usingSample ? '1' : undefined}
      aria-label={
        surface === 'positions'
          ? STOCK_VIEW_MODULE_POSITIONS_TITLE
          : surface === 'nova_os'
            ? STOCK_VIEW_MODULE_NOVA_OS_TITLE
            : ORDERS_TODAY_TITLE
      }
    >
      <header
        className="sv-open-orders-dock__bar"
        onClick={(e) => {
          const el = e.target as HTMLElement;
          if (el.closest('.sv-open-orders-dock__sample-btn')) return;
          if (el.closest('.sv-open-orders-dock__tabs')) return;
          if (el.closest('.orders-today-filters')) return;
          toggle();
        }}
      >
        <button
          type="button"
          className="sv-open-orders-dock__toggle"
          onClick={(e) => {
            e.stopPropagation();
            toggle();
          }}
          aria-expanded={!collapsed}
          data-testid="stock-view-open-orders-toggle"
        >
          <span className="sv-open-orders-dock__chevron" aria-hidden="true">
            {collapsed ? '▸' : '▾'}
          </span>
        </button>
        <div
          className="sv-open-orders-dock__tabs"
          role="tablist"
          aria-label="Positions, orders, and Nova OS"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            role="tab"
            aria-selected={surface === 'positions'}
            className={
              surface === 'positions'
                ? 'sv-open-orders-dock__tab is-active'
                : 'sv-open-orders-dock__tab'
            }
            data-testid="stock-view-dock-tab-positions"
            onClick={() => selectSurface('positions')}
          >
            {STOCK_VIEW_MODULE_POSITIONS_TITLE}
            <span className="sv-open-orders-dock__count">{positionCount}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={surface === 'orders'}
            className={
              surface === 'orders'
                ? 'sv-open-orders-dock__tab is-active'
                : 'sv-open-orders-dock__tab'
            }
            data-testid="stock-view-dock-tab-orders"
            onClick={() => selectSurface('orders')}
          >
            {ORDERS_TODAY_TITLE}
            <span className="sv-open-orders-dock__count">{openCount}</span>
            {usingSample && (
              <span className="sv-open-orders-dock__sample-tag">Sample</span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={surface === 'nova_os'}
            className={
              surface === 'nova_os'
                ? 'sv-open-orders-dock__tab is-active'
                : 'sv-open-orders-dock__tab'
            }
            data-testid="stock-view-dock-tab-nova-os"
            onClick={() => selectSurface('nova_os')}
          >
            {STOCK_VIEW_MODULE_NOVA_OS_TITLE}
          </button>
        </div>
        {surface === 'orders' && usingSample ? (
          <button
            type="button"
            className="sv-open-orders-dock__sample-btn"
            onClick={(e) => {
              e.stopPropagation();
              hideSample();
            }}
          >
            Hide sample
          </button>
        ) : surface === 'orders' &&
          wantsWorkingSample &&
          symbolOrders.length === 0 ? (
          <button
            type="button"
            className="sv-open-orders-dock__sample-btn"
            onClick={(e) => {
              e.stopPropagation();
              showSample();
            }}
            data-testid="stock-view-open-orders-show-sample"
          >
            Show sample
          </button>
        ) : null}
        <span className="na-muted sv-open-orders-dock__hint">
          {collapsed ? 'Expand' : 'Collapse'}
        </span>
      </header>
      {!collapsed && (
        <div className="sv-open-orders-dock__body">
          {surface === 'positions' ? (
            <div data-testid="stock-view-positions">
              <PositionsPanel
                summary={summary}
                positions={positions}
                orders={[]}
                error={accountError}
                selectedSymbol={symbolKey}
                onSelectSymbol={onSelectSymbol}
                onOpenTrading={onSelectSymbol}
                mode={mode}
                connected={connected}
                spendStatus={spendStatus}
                onPositionClosed={onPositionClosed}
                compact
                hideTitle
              />
            </div>
          ) : surface === 'nova_os' ? (
            <div data-testid="stock-view-nova-os">
              <TraderNovaOsBrain symbol={symbolKey} position={symbolPosition} />
            </div>
          ) : (
            <>
              {usingSample && (
                <p className="sv-open-orders-dock__banner" role="status">
                  {STOCK_VIEW_OPEN_ORDERS_SAMPLE_BANNER}
                </p>
              )}
              <OrdersTodayView
                symbol={symbolKey}
                workingOrders={displayOrders}
                usingWorkingSample={usingSample}
                closedOrders={closedOrders}
                onCancelOrder={onCancelOrder}
                onFillImmediately={onFillImmediately}
                highlightOrderId={highlightOrderId}
                filter={filter}
                onFilterChange={selectFilter}
              />
            </>
          )}
        </div>
      )}
    </section>
  );
}
