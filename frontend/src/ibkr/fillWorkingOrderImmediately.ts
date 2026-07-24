/**
 * Fill now — cancel a working order, then market the remaining qty (same side).
 * Distinct from Flatten (position exit) and from Cancel alone (leaves fills as-is).
 * Uses ADR 007 place + cancel paths only. auto_live remains NO-GO.
 */
import {
  APP_DIALOG_FILL_LABEL,
  FILL_WORKING_ORDER_CONFIRM_PREFIX,
} from '../constants';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
  type BrowserActionStamp,
} from '../execution_latency';
import { confirmApp } from '../ux';
import { cancelIbkrOrder } from './cancelOrder';
import { shouldUseOutsideRth } from './extendedSession';
import { remainingSharesWhole } from './orderQtyMath';
import { placeIbkrOrder, type PlaceOrderResult } from './placeOrder';
import type { IbkrOrder } from './types';

export type FillWorkingOrderResult =
  | {
      ok: true;
      cancelled_order_id: number;
      place_order_id: number | null;
      side: 'BUY' | 'SELL';
      qty: number;
      outside_rth: boolean;
      mode?: string;
    }
  | { ok: false; error: string; place?: PlaceOrderResult };

/** Confirm dialog then fill — for panel buttons. */
export async function confirmAndFillWorkingOrder(
  order: IbkrOrder,
): Promise<FillWorkingOrderResult> {
  const actionTiming = captureBrowserAction('user_action');
  const qty = remainingSharesWhole(order);
  if (qty <= 0) {
    return { ok: false, error: 'Nothing left to fill on this order' };
  }
  const side = order.side === 'SELL' ? 'SELL' : 'BUY';
  const outside_rth = shouldUseOutsideRth(order.outside_rth);
  const hours = outside_rth ? ' (extended hours)' : '';
  const ok = await confirmApp({
    title: 'Fill working order now?',
    message: `${FILL_WORKING_ORDER_CONFIRM_PREFIX}: ${side} ${qty} ${order.symbol.toUpperCase()}${hours}?`,
    confirmLabel: APP_DIALOG_FILL_LABEL,
    tone: 'warning',
  });
  if (!ok) {
    return { ok: false, error: 'Fill now cancelled' };
  }
  return fillWorkingOrderImmediately(order, actionTiming);
}

export async function fillWorkingOrderImmediately(
  order: IbkrOrder,
  actionTiming: BrowserActionStamp = captureBrowserAction('client_call'),
): Promise<FillWorkingOrderResult> {
  const qty = remainingSharesWhole(order);
  if (qty <= 0) {
    return { ok: false, error: 'Nothing left to fill on this order' };
  }
  const side = order.side === 'SELL' ? 'SELL' : 'BUY';
  const outside_rth = shouldUseOutsideRth(order.outside_rth);

  try {
    const cancel = await cancelIbkrOrder(
      order.order_id,
      beginBrowserExecutionTiming('fill_now_cancel', actionTiming),
    );
    if (!cancel.ok) {
      return {
        ok: false,
        error: cancel.error ?? `Cancel failed (HTTP ${cancel.httpStatus})`,
      };
    }
  } catch {
    return { ok: false, error: 'Network error cancelling order' };
  }

  try {
    const place = await placeIbkrOrder(
      {
        symbol: order.symbol.trim().toUpperCase(),
        side,
        qty,
        order_type: 'MKT',
        outside_rth,
      },
      undefined,
      {
        timing: beginBrowserExecutionTiming('fill_now_place', actionTiming),
        referencePrice: order.avg_fill_price ?? order.limit_price,
      },
    );
    if (!place.ok) {
      return {
        ok: false,
        error:
          place.error
          ?? 'Order cancelled but market fill failed — check Working Orders / Positions',
        place,
      };
    }
    return {
      ok: true,
      cancelled_order_id: order.order_id,
      place_order_id: place.order_id,
      side,
      qty,
      outside_rth,
      mode: place.mode,
    };
  } catch {
    return {
      ok: false,
      error:
        'Order cancelled but network error placing market fill — check Working Orders / Positions',
    };
  }
}
