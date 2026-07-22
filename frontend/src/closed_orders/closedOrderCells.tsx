/** Cell renderers for Closed Orders columns. */
import type { ReactNode } from 'react';
import {
  formatOrderDateTime,
  formatOrderType,
  orderFilledTimeTitle,
  orderSubmittedTimeTitle,
} from '../ibkr/orderDisplay';
import type { ClosedOrderColumnId } from '../ibkr/orderTableColumns';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import type { ClosedOrder } from './types';

export type ClosedCellCtx = {
  statusLabel: string;
  tone: string;
  /** Time Placed ISO (submitted_at) — never last fill/cancel. */
  placedIso: string | null;
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
          {formatShareQty(o.qty)}
        </td>
      );
    case 'filled': {
      const filled = o.filled_qty ?? 0;
      return (
        <td
          key={col}
          className="ibkr-col--num"
          title={`${formatShareQty(filled)} of ${formatShareQty(o.qty)} shares filled`}
        >
          {formatShareQty(filled)}
        </td>
      );
    }
    case 'type':
      return (
        <td key={col} className="ibkr-col--type ibkr-order-type">
          {formatOrderType(o.order_type)}
        </td>
      );
    case 'limit':
      return (
        <td key={col} className="ibkr-col--num">
          {formatMoney(o.limit_price)}
        </td>
      );
    case 'avg_fill':
      return (
        <td key={col} className="ibkr-col--num">
          {formatMoney(o.avg_fill_price ?? null)}
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
        <td key={col} className="ibkr-col--time" title={orderSubmittedTimeTitle(o)}>
          <time dateTime={ctx.placedIso ?? undefined}>
            {formatOrderDateTime(ctx.placedIso)}
          </time>
        </td>
      );
    case 'filled_at':
      return (
        <td key={col} className="ibkr-col--time" title={orderFilledTimeTitle(o)}>
          <time dateTime={o.filled_at ?? undefined}>
            {formatOrderDateTime(o.filled_at)}
          </time>
        </td>
      );
    default:
      return null;
  }
}
