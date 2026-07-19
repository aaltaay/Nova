/** Cell renderers for Closed Orders columns. */
import type { ReactNode } from 'react';
import {
  formatOrderDateTime,
  formatOrderType,
  orderTimeTitle,
} from '../ibkr/orderDisplay';
import type { ClosedOrderColumnId } from '../ibkr/orderTableColumns';
import type { ClosedOrder } from './types';

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

export type ClosedCellCtx = {
  statusLabel: string;
  tone: string;
  activityIso: string | null;
  sideCls: string;
  sideLabel: string;
};

export function renderClosedOrderCell(
  col: ClosedOrderColumnId,
  o: ClosedOrder,
  ctx: ClosedCellCtx,
): ReactNode {
  switch (col) {
    case 'order_id':
      return (
        <td key={col} className="ibkr-col--text ibkr-order-id">
          {o.order_id}
        </td>
      );
    case 'symbol':
      return (
        <td
          key={col}
          className={`ibkr-col--text ibkr-symbol ${ctx.sideCls}`}
          title={ctx.sideLabel}
          data-side={o.side}
        >
          {o.symbol}
        </td>
      );
    case 'qty':
      return (
        <td key={col} className={`ibkr-col--num ${ctx.sideCls}`} title={ctx.sideLabel}>
          {fmt(o.qty, 0)}
        </td>
      );
    case 'filled':
      return (
        <td key={col} className="ibkr-col--num">
          {fmt(o.filled_qty ?? 0, 0)}
        </td>
      );
    case 'type':
      return (
        <td key={col} className="ibkr-col--type ibkr-order-type">
          {formatOrderType(o.order_type)}
        </td>
      );
    case 'limit':
      return (
        <td key={col} className="ibkr-col--num">
          {fmtDollar(o.limit_price)}
        </td>
      );
    case 'avg_fill':
      return (
        <td key={col} className="ibkr-col--num">
          {fmtDollar(o.avg_fill_price ?? null)}
        </td>
      );
    case 'status':
      return (
        <td key={col} className="ibkr-col--status">
          <span
            className={`ibkr-order-status ibkr-order-status--${ctx.tone}`}
            title={o.status}
          >
            {ctx.statusLabel}
          </span>
        </td>
      );
    case 'time':
      return (
        <td key={col} className="ibkr-col--time" title={orderTimeTitle(o)}>
          <time dateTime={ctx.activityIso ?? undefined}>
            {formatOrderDateTime(ctx.activityIso)}
          </time>
        </td>
      );
    default:
      return null;
  }
}
