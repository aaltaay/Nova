/** Cell renderers for Working Orders columns (keeps panel under size limit). */
import type { ReactNode } from 'react';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import {
  formatExtendedHours,
  formatOrderDateTime,
  formatOrderType,
  orderSubmittedTimeTitle,
} from './orderDisplay';
import { remainingShares } from './orderQtyMath';
import type { WorkingOrderColumnId } from './orderTableColumns';
import type { IbkrOrder } from './types';

export type WorkingCellCtx = {
  statusLabel: string;
  tone: string;
  /** Time Placed ISO (submitted_at) — never updated_at. */
  placedIso: string | null;
  sideCls: string;
  sideLabel: string;
};

export function renderWorkingOrderCell(
  col: WorkingOrderColumnId,
  o: IbkrOrder,
  ctx: WorkingCellCtx,
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
    case 'remaining': {
      const rem = remainingShares(o);
      return (
        <td
          key={col}
          className="ibkr-col--num"
          title={`${formatShareQty(rem)} shares still working`}
        >
          {formatShareQty(rem)}
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
    case 'stop':
      return (
        <td key={col} className="ibkr-col--num">
          {formatMoney(o.stop_price ?? null)}
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
    case 'session':
      return (
        <td key={col} className="ibkr-col--type ibkr-order-session">
          {formatExtendedHours(Boolean(o.outside_rth))}
        </td>
      );
    default:
      return null;
  }
}
