/**
 * Full-position flatten via the manual IBKR place path (ADR 007).
 * Same route as Nova Action `exit_pos` / Stock View Flatten — not a second broker path.
 * Distinct from cancel-working-order (DELETE /api/ibkr/order/{id}).
 *
 * Extended hours: when `outsideRth` is true (or auto-detected), sends MKT with
 * outside_rth so Flatten can work in pre/after-market. RTH defaults to false.
 */
import {
  beginBrowserExecutionTiming,
  type BrowserActionStamp,
} from '../execution_latency';
import { shouldUseOutsideRth } from './extendedSession';
import { buildExitFullPosition } from './exitPosition';
import { placeIbkrOrder, type PlaceOrderResult } from './placeOrder';

export type CloseFullPositionResult =
  | { ok: true; order_id: number | null; side: 'BUY' | 'SELL'; qty: number; mode?: string; outside_rth: boolean }
  | { ok: false; error: string; place?: PlaceOrderResult };

export async function closeFullPosition(
  symbol: string,
  positionQty: number | null | undefined,
  options?: {
    outsideRth?: boolean;
    timingAction?: BrowserActionStamp;
    referencePrice?: number | null;
  },
): Promise<CloseFullPositionResult> {
  const built = buildExitFullPosition(positionQty);
  if (!built.ok) {
    return { ok: false, error: built.error };
  }
  const sym = symbol.trim().toUpperCase();
  if (!sym) {
    return { ok: false, error: 'No symbol to close' };
  }
  const outside_rth =
    options?.outsideRth !== undefined
      ? Boolean(options.outsideRth)
      : shouldUseOutsideRth(false);
  const timing = beginBrowserExecutionTiming(
    'flatten_position',
    options?.timingAction,
  );
  try {
    const res = await placeIbkrOrder(
      {
        symbol: sym,
        side: built.side,
        qty: built.qty,
        order_type: 'MKT',
        outside_rth,
      },
      undefined,
      { timing, referencePrice: options?.referencePrice },
    );
    if (!res.ok) {
      return { ok: false, error: res.error ?? 'Close failed', place: res };
    }
    return {
      ok: true,
      order_id: res.order_id,
      side: built.side,
      qty: built.qty,
      mode: res.mode,
      outside_rth,
    };
  } catch {
    return { ok: false, error: 'Network error placing close' };
  }
}
