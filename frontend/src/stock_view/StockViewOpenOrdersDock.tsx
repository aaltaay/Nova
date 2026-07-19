/**
 * Collapsible Stock View orders strip (WID-026 / WID-027).
 * Tabs: Open Orders (working) | Closed Orders (filled/cancelled) — Closed uses
 * the isolated closed_orders feature slice (hide/move/drag-drop ready).
 */
import { useEffect, useMemo, useState } from 'react';
import { ClosedOrdersModule } from '../closed_orders';
import { buildMockWorkingOrders } from '../ibkr/mockWorkingOrders';
import { WorkingOrdersPanel } from '../ibkr/WorkingOrdersPanel';
import type { IbkrOrder } from '../ibkr/types';
import {
  CLOSED_ORDERS_PANEL_TITLE,
  STOCK_VIEW_MODULE_WORKING_ORDERS_TITLE,
  STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
  STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
  STOCK_VIEW_OPEN_ORDERS_SAMPLE_BANNER,
  STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY,
  STOCK_VIEW_ORDERS_TAB_DEFAULT,
  STOCK_VIEW_ORDERS_TAB_KEY,
  type StockViewOrdersTab,
} from '../constants';

type Props = {
  symbol: string;
  orders: IbkrOrder[];
  onCancelOrder?: (id: number) => void;
  highlightOrderId?: number | null;
  /** Lets Stock View show/hide the charts↔orders resize handle. */
  onCollapsedChange?: (collapsed: boolean) => void;
};

function readCollapsed(): boolean {
  try {
    const raw = localStorage.getItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY);
    if (raw === '1') return true;
    if (raw === '0') return false;
  } catch {
    /* private mode */
  }
  return STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED;
}

function writeCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(
      STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
      collapsed ? '1' : '0',
    );
  } catch {
    /* ignore */
  }
}

function readSampleHidden(): boolean {
  try {
    return localStorage.getItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY) === '1';
  } catch {
    return false;
  }
}

function readTab(): StockViewOrdersTab {
  try {
    const raw = localStorage.getItem(STOCK_VIEW_ORDERS_TAB_KEY);
    if (raw === 'closed' || raw === 'open') return raw;
  } catch {
    /* ignore */
  }
  return STOCK_VIEW_ORDERS_TAB_DEFAULT;
}

function writeTab(tab: StockViewOrdersTab): void {
  try {
    localStorage.setItem(STOCK_VIEW_ORDERS_TAB_KEY, tab);
  } catch {
    /* ignore */
  }
}

export function StockViewOpenOrdersDock({
  symbol,
  orders,
  onCancelOrder,
  highlightOrderId = null,
  onCollapsedChange,
}: Props) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [sampleHidden, setSampleHidden] = useState(readSampleHidden);
  const [tab, setTab] = useState<StockViewOrdersTab>(readTab);

  useEffect(() => {
    onCollapsedChange?.(collapsed);
  }, [collapsed, onCollapsedChange]);

  const symbolKey = symbol.toUpperCase();
  const symbolOrders = useMemo(
    () => orders.filter((o) => o.symbol.toUpperCase() === symbolKey),
    [orders, symbolKey],
  );
  const usingSample = tab === 'open' && symbolOrders.length === 0 && !sampleHidden;
  const displayOrders = useMemo(
    () => (usingSample ? buildMockWorkingOrders(symbolKey) : orders),
    [usingSample, symbolKey, orders],
  );
  const openCount = usingSample ? displayOrders.length : symbolOrders.length;

  useEffect(() => {
    if (highlightOrderId != null || symbolOrders.length > 0 || usingSample) {
      setCollapsed(false);
      writeCollapsed(false);
    }
  }, [highlightOrderId, symbolOrders.length, usingSample]);

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  };

  const selectTab = (next: StockViewOrdersTab) => {
    setTab(next);
    writeTab(next);
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
      data-orders-tab={tab}
      data-sample={usingSample ? '1' : undefined}
      aria-label={
        tab === 'closed'
          ? CLOSED_ORDERS_PANEL_TITLE
          : STOCK_VIEW_MODULE_WORKING_ORDERS_TITLE
      }
    >
      <header
        className="sv-open-orders-dock__bar"
        onClick={(e) => {
          const el = e.target as HTMLElement;
          if (el.closest('.sv-open-orders-dock__sample-btn')) return;
          if (el.closest('.sv-open-orders-dock__tabs')) return;
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
          aria-label="Orders dock"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'open'}
            className={
              tab === 'open'
                ? 'sv-open-orders-dock__tab is-active'
                : 'sv-open-orders-dock__tab'
            }
            data-testid="stock-view-orders-tab-open"
            onClick={() => selectTab('open')}
          >
            {STOCK_VIEW_MODULE_WORKING_ORDERS_TITLE}
            <span className="sv-open-orders-dock__count">{openCount}</span>
            {usingSample && (
              <span className="sv-open-orders-dock__sample-tag">Sample</span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'closed'}
            className={
              tab === 'closed'
                ? 'sv-open-orders-dock__tab is-active'
                : 'sv-open-orders-dock__tab'
            }
            data-testid="stock-view-orders-tab-closed"
            onClick={() => selectTab('closed')}
          >
            {CLOSED_ORDERS_PANEL_TITLE}
          </button>
        </div>
        {tab === 'open' && usingSample ? (
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
        ) : tab === 'open' && symbolOrders.length === 0 ? (
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
      {!collapsed && tab === 'open' && (
        <div className="sv-open-orders-dock__body" data-testid="stock-view-working-orders">
          {usingSample && (
            <p className="sv-open-orders-dock__banner" role="status">
              {STOCK_VIEW_OPEN_ORDERS_SAMPLE_BANNER}
            </p>
          )}
          <WorkingOrdersPanel
            orders={displayOrders}
            filterSymbol={symbol}
            hideTitle
            compact={false}
            onCancelOrder={usingSample ? undefined : onCancelOrder}
            highlightOrderId={usingSample ? 90001 : highlightOrderId}
          />
        </div>
      )}
      {!collapsed && tab === 'closed' && (
        <div
          className="sv-open-orders-dock__body"
          data-testid="stock-view-closed-orders"
        >
          <ClosedOrdersModule
            filterSymbol={symbol}
            selectedSymbol={symbol}
            hideTitle
          />
        </div>
      )}
    </section>
  );
}
