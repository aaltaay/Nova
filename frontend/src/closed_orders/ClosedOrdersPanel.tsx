/**
 * Closed Orders — Webull History / filled+cancelled lifecycle (WID-027).
 * Isolated feature slice (ADR 005). No cancel controls — cancel lives on Working Orders.
 */
import { useMemo, useState } from 'react';
import { SelectableTableRow } from '../components/SelectableTableRow';
import {
  CLOSED_ORDERS_EMPTY_MESSAGE,
  CLOSED_ORDERS_PANEL_TITLE,
  CLOSED_ORDERS_SAMPLE_BANNER,
} from '../constants';
import {
  formatOrderSide,
  formatOrderStatus,
  formatOrderType,
  orderStatusTone,
} from '../ibkr/orderDisplay';
import { filterClosedOrders } from './filterClosedOrders';
import type { ClosedOrder, ClosedOrdersFilter } from './types';

interface Props {
  orders: ClosedOrder[];
  selectedSymbol?: string | null;
  onSelectSymbol?: (symbol: string) => void;
  onOpenTrading?: (symbol: string) => void;
  filterSymbol?: string | null;
  hideTitle?: boolean;
  /** When true, show sample banner (mock rows). */
  sampleMode?: boolean;
}

function fmt(n: number | null | undefined, decimals = 2) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtDollar(n: number | null | undefined) {
  if (n == null) return '—';
  return `$${fmt(n)}`;
}

function sideColor(side: string) {
  return side.trim().toUpperCase() === 'BUY' ? 'var(--green)' : 'var(--red)';
}

const FILTERS: { id: ClosedOrdersFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'filled', label: 'Filled' },
  { id: 'cancelled', label: 'Cancelled' },
];

export function ClosedOrdersPanel({
  orders,
  selectedSymbol = null,
  onSelectSymbol,
  onOpenTrading,
  filterSymbol = null,
  hideTitle = false,
  sampleMode = false,
}: Props) {
  const [filter, setFilter] = useState<ClosedOrdersFilter>('all');
  const rows = useMemo(
    () => filterClosedOrders(orders, filter, filterSymbol),
    [orders, filter, filterSymbol],
  );

  return (
    <div
      className="ibkr-closed-orders"
      data-testid="closed-orders-panel"
      data-module="closed_orders"
      data-sample={sampleMode ? '1' : undefined}
    >
      {!hideTitle && (
        <div className="ibkr-closed-orders-header">
          <h4 className="ibkr-section-title">{CLOSED_ORDERS_PANEL_TITLE}</h4>
          <p className="ibkr-closed-orders-hint">
            Filled and cancelled session orders. To remove a working order, use Cancel on
            Working Orders — Flatten on Positions closes the whole position.
          </p>
        </div>
      )}
      {sampleMode && (
        <div className="ibkr-sample-banner" data-testid="closed-orders-sample-banner">
          {CLOSED_ORDERS_SAMPLE_BANNER}
        </div>
      )}
      <div className="ibkr-closed-orders-filters" role="tablist" aria-label="Closed order filter">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filter === f.id}
            className={
              filter === f.id
                ? 'ibkr-closed-orders-filter active'
                : 'ibkr-closed-orders-filter'
            }
            data-filter={f.id}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="ibkr-empty">{CLOSED_ORDERS_EMPTY_MESSAGE}</div>
      ) : (
        <table className="ibkr-table ibkr-table--orders">
          <thead>
            <tr>
              <th>Order ID</th>
              <th title="Click: Quote Panel · Double-click: Stock View">Symbol</th>
              <th>Side</th>
              <th>Quantity</th>
              <th>Filled</th>
              <th>Type</th>
              <th>Limit price</th>
              <th>Average fill</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => {
              const statusLabel = formatOrderStatus(
                o.status,
                o.filled_qty ?? 0,
                o.qty,
              );
              const tone = orderStatusTone(statusLabel);
              const cells = (
                <>
                  <td className="ibkr-order-id">{o.order_id}</td>
                  <td className="ibkr-symbol">{o.symbol}</td>
                  <td style={{ color: sideColor(o.side) }}>{formatOrderSide(o.side)}</td>
                  <td>{fmt(o.qty, 0)}</td>
                  <td>{fmt(o.filled_qty ?? 0, 0)}</td>
                  <td className="ibkr-order-type">{formatOrderType(o.order_type)}</td>
                  <td>{fmtDollar(o.limit_price)}</td>
                  <td>{fmtDollar(o.avg_fill_price ?? null)}</td>
                  <td>
                    <span
                      className={`ibkr-order-status ibkr-order-status--${tone}`}
                      title={o.status}
                    >
                      {statusLabel}
                    </span>
                  </td>
                </>
              );
              if (onSelectSymbol && onOpenTrading) {
                return (
                  <SelectableTableRow
                    key={o.order_id}
                    symbol={o.symbol}
                    selected={selectedSymbol === o.symbol}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                  >
                    {cells}
                  </SelectableTableRow>
                );
              }
              return <tr key={o.order_id}>{cells}</tr>;
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
