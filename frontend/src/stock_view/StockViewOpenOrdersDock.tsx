/**
 * Collapsible Working Orders strip at the bottom of Stock View (WID-026).
 * Webull-style open/working table under the chart workspace — user can collapse.
 */
import { useEffect, useMemo, useState } from 'react';
import { WorkingOrdersPanel } from '../ibkr/WorkingOrdersPanel';
import type { IbkrOrder } from '../ibkr/types';
import {
  STOCK_VIEW_MODULE_WORKING_ORDERS_TITLE,
  STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
  STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
} from '../constants';

type Props = {
  symbol: string;
  orders: IbkrOrder[];
  onCancelOrder?: (id: number) => void;
  highlightOrderId?: number | null;
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

export function StockViewOpenOrdersDock({
  symbol,
  orders,
  onCancelOrder,
  highlightOrderId = null,
}: Props) {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const symbolKey = symbol.toUpperCase();
  const symbolOrders = useMemo(
    () => orders.filter((o) => o.symbol.toUpperCase() === symbolKey),
    [orders, symbolKey],
  );
  const count = symbolOrders.length;

  // After a place (or when working orders appear), expand so the user sees them.
  useEffect(() => {
    if (highlightOrderId != null || count > 0) {
      setCollapsed(false);
      writeCollapsed(false);
    }
  }, [highlightOrderId, count]);

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  };

  return (
    <section
      className={`sv-open-orders-dock${collapsed ? ' sv-open-orders-dock--collapsed' : ''}`}
      data-testid="stock-view-open-orders-dock"
      aria-label={STOCK_VIEW_MODULE_WORKING_ORDERS_TITLE}
    >
      <header className="sv-open-orders-dock__bar">
        <button
          type="button"
          className="sv-open-orders-dock__toggle"
          onClick={toggle}
          aria-expanded={!collapsed}
          data-testid="stock-view-open-orders-toggle"
        >
          <span className="sv-open-orders-dock__chevron" aria-hidden="true">
            {collapsed ? '▸' : '▾'}
          </span>
          <span className="sv-open-orders-dock__title">
            {STOCK_VIEW_MODULE_WORKING_ORDERS_TITLE}
          </span>
          <span className="sv-open-orders-dock__count">{count}</span>
        </button>
        <span className="na-muted sv-open-orders-dock__hint">
          {collapsed ? 'Expand open orders' : 'Collapse'}
        </span>
      </header>
      {!collapsed && (
        <div className="sv-open-orders-dock__body" data-testid="stock-view-working-orders">
          <WorkingOrdersPanel
            orders={orders}
            filterSymbol={symbol}
            hideTitle
            compact={false}
            onCancelOrder={onCancelOrder}
            highlightOrderId={highlightOrderId}
          />
        </div>
      )}
    </section>
  );
}
