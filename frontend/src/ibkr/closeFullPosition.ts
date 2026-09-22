/**
 * Full-position flatten via the manual IBKR place path (ADR 007).
 * Same route as Nova Action `exit_pos` / Stock View Flatten -- not a second broker path.
 * Distinct from cancel-working-order (DELETE /api/ibkr/order/{id}).
 *
 * Weekday RTH: MKT outside_rth=false.
 * After hours / weekend: EH LMT at bid/ask/last (same ticket as Fill now).
 * "RTH" is judged by the venue's clock -- the Sim playhead on Sim (QA R21).
 */
import {
  beginBrowserExecutionTiming,
  type BrowserActionStamp,
} from '../execution_latency';
import { beginDeskAction } from './deskActionFlight';
import { buildExitFullPosition } from './exitPosition';
import { venueClockNow } from './marketOutsideRth';
import { planFlattenExit, type FlattenExitBook } from './planFlattenExit';
import { placeIbkrOrder, type PlaceOrderResult } from './placeOrder';

export type CloseFullPositionResult =
  | {
      ok: true;
      order_id: number | null;
      side: 'BUY' | 'SELL';
      qty: number;
      mode?: string;
      outside_rth: boolean;
      order_type: 'MKT' | 'LMT';
    }
  | { ok: false; error: string; place?: PlaceOrderResult };

export async function closeFullPosition(
  symbol: string,
  positionQty: number | null | undefined,
  options?: {
    outsideRth?: boolean;
    timingAction?: BrowserActionStamp;
    referencePrice?: number | null;
    book?: FlattenExitBook | null;
    /** The desk's venue: on Sim the flatten plans against the playhead, not the wall clock (R21). */
    mode?: string | null;
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
  const book: FlattenExitBook = {
    bid: options?.book?.bid,
    ask: options?.book?.ask,
    last: options?.book?.last ?? options?.referencePrice,
  };
  const ticket = planFlattenExit(built.side, {
    outsideRth: options?.outsideRth,
    book,
    now: venueClockNow(options?.mode),
  });
  if (!ticket.ok) {
    return { ok: false, error: ticket.error };
  }
  const timing = beginBrowserExecutionTiming(
    'flatten_position',
    options?.timingAction,
  );
  const endDeskAction = beginDeskAction();
  try {
    const res = await placeIbkrOrder(
      {
        symbol: sym,
        side: built.side,
        qty: built.qty,
        order_type: ticket.order_type,
        outside_rth: ticket.outside_rth,
        limit_price: ticket.limit_price,
        intent: 'flatten',
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
      outside_rth: ticket.outside_rth,
      order_type: ticket.order_type,
    };
  } catch {
    return { ok: false, error: 'Network error placing close' };
  } finally {
    endDeskAction();
  }
}
