import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { sampleOrderRefusal } from '../sample_data/sampleOrderGuard';
import { executionTransportError } from './executionTransportError';
import { newGestureKey } from './gestureKey';
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
  reason_code?: string | null;
  mode?: string;
  execution_id?: string;
  duplicate?: boolean;
  timings?: Record<string, number | null> | null;
  broker_status?: string | null;
}

// Callers own the key: pass one per user gesture so a retry of that gesture
// replays instead of placing a second order (see gestureKey.ts).

export async function placeIbkrOrder(
  payload: ManualOrderPayload,
  idempotencyKey?: string,
  options?: {
    timing?: BrowserExecutionTiming;
    referencePrice?: number | null;
  },
): Promise<PlaceOrderResult> {
  // The sample desk never reaches a broker (#357). Refuse before any transport
  // so a sample ticket cannot POST an order at a machine whose backend is up.
  const refusal = sampleOrderRefusal();
  if (refusal) {
    // Close a caller-supplied span so the latency ledger stays honest; a
    // refusal must not open a new one.
    options?.timing?.complete(false);
    return {
      ok: false,
      order_id: null,
      error: refusal,
      reason_code: 'SAMPLE_VIEW',
    };
  }
  const timing = options?.timing ?? beginBrowserExecutionTiming('place_order');
  const clientTiming = timing.clientTimingAtRequest();
  try {
    const response = await novaFetch(`${API_BASE_URL}/api/ibkr/order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...payload,
        idempotency_key: idempotencyKey || newGestureKey('place'),
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
    return {
      ok: false,
      order_id: null,
      error: executionTransportError(error),
    };
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
  const refusal = sampleOrderRefusal();
  if (refusal) {
    // The span is already open (default arg), so close it rather than leave it
    // dangling -- same as the transport-error path below.
    timing.complete(false);
    return { ok: false, cancelled: [], failed: [], error: refusal };
  }
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

/** Cancel every working order on the connected account (ADR 007 per-order cancels). */
export async function cancelAllWorkingOrders(
  timing: BrowserExecutionTiming = beginBrowserExecutionTiming('cancel_all'),
): Promise<CancelAllResult> {
  const refusal = sampleOrderRefusal();
  if (refusal) {
    // The span is already open (default arg), so close it rather than leave it
    // dangling -- same as the transport-error path below.
    timing.complete(false);
    return { ok: false, cancelled: [], failed: [], error: refusal };
  }
  try {
    const response = await novaFetch(
      `${API_BASE_URL}/api/ibkr/orders?all_symbols=true`,
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

/** Count open working orders (for Cancel All confirm copy). */
export async function countOpenWorkingOrders(): Promise<number | null> {
  try {
    const response = await novaFetch(`${API_BASE_URL}/api/ibkr/orders`);
    if (!response.ok) return null;
    const data = (await response.json()) as unknown;
    if (Array.isArray(data)) return data.length;
    return null;
  } catch {
    return null;
  }
}
