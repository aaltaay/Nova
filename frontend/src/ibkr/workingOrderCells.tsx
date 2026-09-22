/** Cell renderers for Working Orders columns (keeps panel under size limit). */
import type { ReactNode } from 'react';
import { formatMoney } from '../utils/formatMoney';
import { formatShareQty } from '../utils/formatShareQty';
import {
  formatOrderDateTime,
  formatOrderSession,
  formatOrderType,
  orderSubmittedTimeTitle,
  plausiblePrice,
} from './orderDisplay';
import { sessionKindNow } from './extendedSession';
import { FillLatencyTd } from './FillLatencyCell';
import { commissionCellTitle, formatCommission } from './orderCommission';
import { displayFilledQty, practiceFillTitle } from './orderFillHonesty';
import { remainingShares } from './orderQtyMath';
import type { WorkingOrderColumnId } from './orderTableColumns';
import type { IbkrOrder } from './types';
import { workingOrderStatusDisplay } from './workingOrderFillability';

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
          {formatMoney(plausiblePrice(o.limit_price))}
        </td>
      );
    case 'stop': {
      const compact = (o.order_type || '').toUpperCase().replace(/[\s_-]+/g, '');
      const stop = plausiblePrice(o.stop_price);
      const stopTitle =
        compact === 'TRAIL' || compact === 'TRAILINGSTOP'
          ? `Trail ${formatMoney(stop)}`
          : undefined;
      return (
        <td key={col} className="ibkr-col--num" title={stopTitle}>
          {formatMoney(stop)}
        </td>
      );
    }
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
    case 'status': {
      const shown = workingOrderStatusDisplay(
        o,
        ctx.statusLabel,
        sessionKindNow(),
      );
      return (
        <td key={col} className="ibkr-col--status">
          <span
            className={`ibkr-order-status ibkr-order-status--${ctx.tone}`}
            title={shown.title}
          >
            {shown.label}
          </span>
        </td>
      );
    }
    case 'time':
      return (
        <td key={col} className="ibkr-col--time" title={orderSubmittedTimeTitle(o)}>
          <time dateTime={ctx.placedIso ?? undefined}>
            {formatOrderDateTime(ctx.placedIso)}
          </time>
        </td>
      );
    case 'session': {
      const session = formatOrderSession(o);
      return (
        <td key={col} className="ibkr-col--type ibkr-order-session" title={session.title}>
          {session.label}
        </td>
      );
    }
    default:
      return null;
  }
}
