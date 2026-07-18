import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
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
): Promise<PlaceOrderResult> {
  const response = await novaFetch(`${API_BASE_URL}/api/ibkr/order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      idempotency_key: idempotencyKey || newIdempotencyKey(),
    }),
  });
  return response.json() as Promise<PlaceOrderResult>;
}

export interface CancelAllResult {
  ok: boolean;
  symbol?: string;
  cancelled: number[];
  failed: { order_id: number; error?: string | null }[];
  error: string | null;
}

/** Cancel all open orders for a symbol (backend orchestrates per-order cancels). */
export async function cancelAllOrdersForSymbol(symbol: string): Promise<CancelAllResult> {
  const response = await novaFetch(
    `${API_BASE_URL}/api/ibkr/orders?symbol=${encodeURIComponent(symbol.toUpperCase())}`,
    { method: 'DELETE' },
  );
  return response.json() as Promise<CancelAllResult>;
}
