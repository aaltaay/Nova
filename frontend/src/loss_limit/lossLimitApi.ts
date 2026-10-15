/** `GET` / `PUT /api/loss-limit` (ADR 056; `architecture/schema/loss-limit.md`). */
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { LOSS_LIMIT_API_PATH } from './lossLimitWords';

export type LossLimitAccountId = 'live' | 'paper' | 'sim';

export interface LossLimitSettings {
  limit_usd: number;
  warn: boolean;
  no_new_buys: boolean;
  auto_sell: boolean;
  set_at: number | null;
  source: 'operator' | 'default';
  error: string | null;
}

export interface LossLimitClose {
  symbol: string;
  side: string;
  qty: number;
  ok: boolean;
  order_id: number | null;
  error: string | null;
}

export interface LossLimitAccount {
  name: string;
  counted_at: number | null;
  pnl: number | null;
  loss: number | null;
  unknown: string | null;
  warned_at: number | null;
  warned_loss: number | null;
  tripped_at: number | null;
  tripped_loss: number | null;
  limit_usd: number | null;
  sold: LossLimitClose[] | null;
  sell_error: string | null;
  no_new_buys: { text: string; until: number } | null;
}

export interface LossLimitView {
  schema_version: number;
  settings: LossLimitSettings;
  day: string | null;
  until: number;
  accounts: Partial<Record<LossLimitAccountId, LossLimitAccount>>;
  error: string | null;
}

export type LossLimitPatch = Partial<Pick<LossLimitSettings, 'limit_usd' | 'warn' | 'no_new_buys' | 'auto_sell'>>;

async function request(init: RequestInit = {}): Promise<LossLimitView> {
  const response = await novaFetch(`${API_BASE_URL}${LOSS_LIMIT_API_PATH}`, init);
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
  return body as LossLimitView;
}

export function fetchLossLimit(): Promise<LossLimitView> {
  return request();
}

export function saveLossLimit(patch: LossLimitPatch): Promise<LossLimitView> {
  return request({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
}
