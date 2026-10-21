/** `GET` / `PUT /api/order-size-limit` (ADR 064; `architecture/schema/execution.md`). */
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { ORDER_SIZE_LIMIT_API_PATH } from './orderSizeLimitWords';

export type OrderSizeLimitVenue = 'paper' | 'sim';
export type OrderSizeLimitField = 'max_shares' | 'max_risk_usd';

/** Whole shares / whole dollars, or null for no limit. */
export type OrderSizeLimitRow = Record<OrderSizeLimitField, number | null>;

export interface OrderSizeLimitSettings {
  venues: Record<OrderSizeLimitVenue, OrderSizeLimitRow>;
  set_at: number | null;
  /** `unreadable`: a saved file Nova cannot use -- Paper and Sim refuse your new orders until the next save. */
  source: 'operator' | 'default' | 'unreadable';
  error: string | null;
}

export interface OrderSizeLimitView {
  schema_version: number;
  settings: OrderSizeLimitSettings;
  rules: {
    venues: OrderSizeLimitVenue[];
    min_shares: number;
    max_shares: number;
    min_risk_usd: number;
    max_risk_usd: number;
  };
}

export type OrderSizeLimitPatch = Partial<Record<OrderSizeLimitVenue, Partial<OrderSizeLimitRow>>>;

async function request(init: RequestInit = {}): Promise<OrderSizeLimitView> {
  const response = await novaFetch(`${API_BASE_URL}${ORDER_SIZE_LIMIT_API_PATH}`, init);
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new Error(typeof detail === 'string' && detail ? detail : `HTTP ${response.status}`);
  }
  if (!body || typeof body !== 'object') throw new Error('Nova returned an unreadable answer');
  return body as OrderSizeLimitView;
}

export function fetchOrderSizeLimit(): Promise<OrderSizeLimitView> {
  return request();
}

export function saveOrderSizeLimit(patch: OrderSizeLimitPatch): Promise<OrderSizeLimitView> {
  return request({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
}
