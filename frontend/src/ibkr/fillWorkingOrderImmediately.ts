/**
 * Fill now -- cancel a working order, then fill the remaining qty (same side).
 * RTH: market. Premarket / AH / overnight: limit sweep at live bid (sell) or
 * ask (buy). Never cancel+resubmit an unfillable EH MKT (#168).
 * Distinct from Flatten (position exit) and from Cancel alone.
 * Uses ADR 007 place + cancel paths only. auto_live remains NO-GO.
 */
import {
  APP_DIALOG_FILL_LABEL,
} from '../constants';
import {
  beginBrowserExecutionTiming,
  captureBrowserAction,
  type BrowserActionStamp,
} from '../execution_latency';
import { confirmApp } from '../ux';
import { cancelIbkrOrder } from './cancelOrder';
import {
  planFillWorkingOrder,
  type FillWorkingBook,
  type FillWorkingPlanOk,
  type PlanFillWorkingOrderOptions,
} from './planFillWorkingOrder';
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
      order_type: 'MKT' | 'LMT';
      limit_price?: number;
      mode?: string;
    }
  | { ok: false; error: string; place?: PlaceOrderResult };

export type FillWorkingOrderOptions = PlanFillWorkingOrderOptions & {
  book?: FillWorkingBook | null;
};

/** Confirm dialog then fill -- for panel buttons. */
export async function confirmAndFillWorkingOrder(
  order: IbkrOrder,
  options?: FillWorkingOrderOptions,
): Promise<FillWorkingOrderResult> {
  const actionTiming = captureBrowserAction('user_action');
  const plan = planFillWorkingOrder(order, options);
  if (!plan.ok) {
    return { ok: false, error: plan.error };
  }
  const ok = await confirmApp({
    title: 'Fill working order now?',
    message: plan.confirmMessage,
    confirmLabel: APP_DIALOG_FILL_LABEL,
    tone: 'warning',
  });
  if (!ok) {
    return { ok: false, error: 'Fill now cancelled' };
  }
  return fillWorkingOrderImmediately(order, actionTiming, options);
}

function placePayload(plan: FillWorkingPlanOk) {
  if (plan.order_type === 'LMT') {
    return {
      symbol: plan.symbol,
      side: plan.side,
      qty: plan.qty,
      order_type: 'LMT' as const,
      limit_price: plan.limit_price,
      outside_rth: true,
    };
  }
  return {
    symbol: plan.symbol,
    side: plan.side,
    qty: plan.qty,
    order_type: 'MKT' as const,
    outside_rth: plan.outside_rth,
  };
}

export async function fillWorkingOrderImmediately(
  order: IbkrOrder,
  actionTiming: BrowserActionStamp = captureBrowserAction('client_call'),
  options?: FillWorkingOrderOptions,
): Promise<FillWorkingOrderResult> {
  const plan = planFillWorkingOrder(order, options);
  if (!plan.ok) {
    return { ok: false, error: plan.error };
  }

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
      placePayload(plan),
      undefined,
      {
        timing: beginBrowserExecutionTiming('fill_now_place', actionTiming),
        referencePrice:
          plan.limit_price
          ?? order.avg_fill_price
          ?? order.limit_price,
      },
    );
    if (!place.ok) {
      return {
        ok: false,
        error:
          place.error
          ?? 'Order cancelled but market fill failed -- check Working Orders / Positions',
        place,
      };
    }
    return {
      ok: true,
      cancelled_order_id: order.order_id,
      place_order_id: place.order_id,
      side: plan.side,
      qty: plan.qty,
      outside_rth: plan.outside_rth,
      order_type: plan.order_type,
      limit_price: plan.limit_price,
      mode: place.mode,
    };
  } catch {
    return {
      ok: false,
      error:
        'Order cancelled but network error placing market fill -- check Working Orders / Positions',
    };
  }
}
