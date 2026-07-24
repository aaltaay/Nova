import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import {
  beginBrowserExecutionTiming,
  clientTimingHeaders,
  parseTimedExecutionResponse,
  type BrowserExecutionTiming,
} from '../execution_latency';
import type { ManualOrderPayload } from './orderEntry';

export interface PlaceOrderResult {
  ok: boolean;
  order_id: number | null;
  error: string | null;
  mode?: string;
  execution_id?: string;
  duplicate?: boolean;
  timings?: Record<string, number | null> | null;
  broker_status?: string | null;
}

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `manual-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function placeIbkrOrder(
  payload: ManualOrderPayload,
  idempotencyKey?: string,
  options?: {
    timing?: BrowserExecutionTiming;
    referencePrice?: number | null;
  },
): Promise<PlaceOrderResult> {
  const timing = options?.timing ?? beginBrowserExecutionTiming('place_order');
  const clientTiming = timing.clientTimingAtRequest();
  try {
    const response = await novaFetch(`${API_BASE_URL}/api/ibkr/order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...payload,
        idempotency_key: idempotencyKey || newIdempotencyKey(),
        reference_price:
          options?.referencePrice != null
          && Number.isFinite(options.referencePrice)
            ? options.referencePrice
            : undefined,
        client_timing: clientTiming,
      }),
    });
    return await parseTimedExecutionResponse<PlaceOrderResult>(response, timing);
  } catch (error) {
    timing.complete(false);
    throw error;
  }
}

export interface CancelAllResult {
  ok: boolean;
  symbol?: string;
  cancelled: number[];
  failed: { order_id: number; error?: string | null }[];
  error: string | null;
}

/** Cancel all open orders for a symbol (backend orchestrates per-order cancels). */
export async function cancelAllOrdersForSymbol(
  symbol: string,
  timing: BrowserExecutionTiming = beginBrowserExecutionTiming('cancel_symbol'),
): Promise<CancelAllResult> {
  try {
    const response = await novaFetch(
      `${API_BASE_URL}/api/ibkr/orders?symbol=${encodeURIComponent(symbol.toUpperCase())}`,
      {
        method: 'DELETE',
        headers: clientTimingHeaders(timing),
      },
    );
    return await parseTimedExecutionResponse<CancelAllResult>(response, timing);
  } catch (error) {
    timing.complete(false);
    throw error;
  }
}
