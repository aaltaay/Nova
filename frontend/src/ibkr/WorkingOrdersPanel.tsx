/**
 * Working Orders table — Webull Orders → Working equivalent (WID-026).
 * Display uses Webull-clean labels; cancel only; no modify / history / auto_live.
 */
import { SelectableTableRow } from '../components/SelectableTableRow';
import { WORKING_ORDERS_PANEL_TITLE } from '../constants';
import {
  formatExtendedHours,
  formatOrderSide,
  formatOrderStatus,
  formatOrderType,
  orderStatusTone,
} from './orderDisplay';
import type { IbkrOrder } from './types';

interface Props {
  orders: IbkrOrder[];
  selectedSymbol?: string | null;
  onSelectSymbol?: (symbol: string) => void;
  onOpenTrading?: (symbol: string) => void;
  onCancelOrder?: (id: number) => void;
  /** Highlight the row for a just-placed order (Trading tab post-place). */
  highlightOrderId?: number | null;
  /** When set, only show orders for this symbol (Stock View rail). */
  filterSymbol?: string | null;
  /** Hide outer section title when embedded in a module card. */
  hideTitle?: boolean;
  compact?: boolean;
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

export function WorkingOrdersPanel({
  orders,
  selectedSymbol = null,
  onSelectSymbol,
  onOpenTrading,
  onCancelOrder,
  highlightOrderId = null,
  filterSymbol = null,
  hideTitle = false,
  compact = false,
}: Props) {
  const filterKey = filterSymbol?.toUpperCase() ?? null;
  const rows = filterKey
    ? orders.filter((o) => o.symbol.toUpperCase() === filterKey)
    : orders;

  return (
    <div
      className={`ibkr-working-orders${compact ? ' ibkr-working-orders--compact' : ''}`}
      data-testid="working-orders-panel"
      data-highlight-order={highlightOrderId ?? undefined}
    >
      {!hideTitle && (
        <h4 className="ibkr-section-title">{WORKING_ORDERS_PANEL_TITLE}</h4>
      )}
      {rows.length === 0 ? (
        <div className="ibkr-empty">No open orders.</div>
      ) : (
        <table className="ibkr-table ibkr-table--orders">
          <thead>
            <tr>
              <th className="ibkr-col--text">Order ID</th>
              <th
                className="ibkr-col--text"
                title="Click: Quote Panel · Double-click: Stock View"
              >
                Symbol
              </th>
              <th className="ibkr-col--side">Side</th>
              <th className="ibkr-col--num">Quantity</th>
              <th className="ibkr-col--num">Filled</th>
              {!compact && <th className="ibkr-col--num">Remaining</th>}
              <th className="ibkr-col--type">Type</th>
              <th className="ibkr-col--num">Limit price</th>
              {!compact && <th className="ibkr-col--num">Stop price</th>}
              <th className="ibkr-col--num">Average fill</th>
              <th className="ibkr-col--status">Status</th>
              {!compact && <th className="ibkr-col--type">Session</th>}
              {onCancelOrder ? <th className="ibkr-col--status"></th> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => {
              const highlighted = highlightOrderId === o.order_id;
              const statusLabel = formatOrderStatus(
                o.status,
                o.filled_qty ?? 0,
                o.qty,
              );
              const tone = orderStatusTone(statusLabel);
              const row = (
                <>
                  <td className="ibkr-col--text ibkr-order-id">{o.order_id}</td>
                  <td className="ibkr-col--text ibkr-symbol">{o.symbol}</td>
                  <td className="ibkr-col--side" style={{ color: sideColor(o.side) }}>
                    {formatOrderSide(o.side)}
                  </td>
                  <td className="ibkr-col--num">{fmt(o.qty, 0)}</td>
                  <td className="ibkr-col--num">{fmt(o.filled_qty ?? 0, 0)}</td>
                  {!compact && (
                    <td className="ibkr-col--num">{fmt(o.remaining_qty ?? null, 0)}</td>
                  )}
                  <td className="ibkr-col--type ibkr-order-type">
                    {formatOrderType(o.order_type)}
                  </td>
                  <td className="ibkr-col--num">{fmtDollar(o.limit_price)}</td>
                  {!compact && (
                    <td className="ibkr-col--num">{fmtDollar(o.stop_price ?? null)}</td>
                  )}
                  <td className="ibkr-col--num">{fmtDollar(o.avg_fill_price ?? null)}</td>
                  <td className="ibkr-col--status">
                    <span
                      className={`ibkr-order-status ibkr-order-status--${tone}`}
                      title={o.status}
                    >
                      {statusLabel}
                    </span>
                  </td>
                  {!compact && (
                    <td className="ibkr-col--type ibkr-order-session">
                      {formatExtendedHours(Boolean(o.outside_rth))}
                    </td>
                  )}
                  {onCancelOrder ? (
                    <td className="ibkr-col--status">
                      <button
                        type="button"
                        className="ibkr-cancel-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onCancelOrder(o.order_id);
                        }}
                        title="Cancel order"
                        aria-label={`Cancel order ${o.order_id}`}
                      >
                        Cancel
                      </button>
                    </td>
                  ) : null}
                </>
              );

              if (onSelectSymbol && onOpenTrading) {
                return (
                  <SelectableTableRow
                    key={o.order_id}
                    symbol={o.symbol}
                    selected={selectedSymbol === o.symbol || highlighted}
                    onSelect={onSelectSymbol}
                    onOpenTrading={onOpenTrading}
                    className={highlighted ? 'ibkr-order-row--highlight' : undefined}
                  >
                    {row}
                  </SelectableTableRow>
                );
              }

              return (
                <tr
                  key={o.order_id}
                  className={highlighted ? 'ibkr-order-row--highlight' : undefined}
                  data-order-id={o.order_id}
                >
                  {row}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
