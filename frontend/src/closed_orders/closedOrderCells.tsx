/** Cell renderers for Closed Orders columns. */
import type { ReactNode } from 'react';
import {
  formatOrderDateTime,
  formatOrderType,
  orderFilledTimeTitle,
  orderSubmittedTimeTitle,
  plausiblePrice,
} from '../ibkr/orderDisplay';
import type { ClosedOrderColumnId } from '../ibkr/orderTableColumns';
import { FillLatencyTd } from '../ibkr/FillLatencyCell';
import { commissionCellTitle, formatCommission } from '../ibkr/orderCommission';
import { displayFilledQty, practiceFillTitle } from '../ibkr/orderFillHonesty';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import { formatClosedOrderId } from './formatClosedOrderId';
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
        <td
          key={col}
          className="ibkr-col--text ibkr-order-id"
          title={
            o.source === 'ib_recovered'
              ? 'IB recovered -- not placed in Nova'
              : o.source === 'nova'
                ? 'Nova ledger'
                : undefined
          }
        >
          {formatClosedOrderId(o)}
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
      const filled = displayFilledQty(o);
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
          {formatMoney(plausiblePrice(o.limit_price))}
        </td>
      );
    case 'avg_fill':
      return (
        <td key={col} className="ibkr-col--num">
          {formatMoney(plausiblePrice(o.avg_fill_price))}
          {o.fill_estimated && o.avg_fill_price != null && (
            <span className="ibkr-fill-estimated" title={practiceFillTitle(o.fill_basis)}>
              est
            </span>
          )}
        </td>
      );
    case 'commission':
      return (
        <td
          key={col}
          className="ibkr-col--num ibkr-col--commission"
          title={commissionCellTitle({
            commission: o.commission,
            avgFill: o.avg_fill_price,
            filledQty: displayFilledQty(o),
          })}
        >
          {formatCommission(o.commission)}
        </td>
      );
    case 'latency':
      return <FillLatencyTd key={col} audit={o.fill_audit} />;
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
