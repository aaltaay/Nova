/** `GET` / `PUT /api/loss-limit` (ADR 056, ADR 061; `architecture/schema/loss-limit.md`). */
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { LOSS_LIMIT_API_PATH } from './lossLimitWords';

export type LossLimitAccountId = 'live' | 'paper' | 'sim';
/** ADR 061: the Account line counts every trade opened today; You and Bots each count one side's. */
export type LossLimitLineId = 'account' | 'you' | 'bots';
export type LossLimitSide = 'you' | 'bots';

export interface LossLimitSettings {
  /** The Account line: every trade opened today, yours and the bots'. */
  limit_usd: number;
  /** Your trades' line; null: no line of your own. */
  you_usd: number | null;
  /** The bots' trades' line; null: no line for the bots. */
  bots_usd: number | null;
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

/** A line that stops new buys now, in the backend's own words. */
export interface LossLimitStop {
  line?: LossLimitLineId;
  text: string;
  until: number;
}

export interface LossLimitLine {
  /** The line is set (the Account line always is). */
  on: boolean;
  pnl: number | null;
  loss: number | null;
  warned_at: number | null;
  warned_loss: number | null;
  tripped_at: number | null;
  tripped_loss: number | null;
  /** The limit when it warned or tripped. */
  limit_usd: number | null;
  /** Auto sell's progress: `pending` until its closes answered (a restart resumes it), then `done`. */
  sell?: 'pending' | 'done' | null;
  sold: LossLimitClose[] | null;
  sell_error: string | null;
  no_new_buys: LossLimitStop | null;
}

export interface LossLimitAccount {
  name: string;
  counted_at: number | null;
  pnl: number | null;
  loss: number | null;
  unknown: string | null;
  lines: Partial<Record<LossLimitLineId, LossLimitLine>>;
  /** Whose new buys are stopped now: the Account line's trip stops both sides. */
  no_new_buys?: Partial<Record<LossLimitSide, LossLimitStop | null>>;
}

export interface LossLimitView {
  schema_version: number;
  settings: LossLimitSettings;
  day: string | null;
  until: number;
  accounts: Partial<Record<LossLimitAccountId, LossLimitAccount>>;
  error: string | null;
}

export type LossLimitPatch = Partial<
  Pick<LossLimitSettings, 'limit_usd' | 'you_usd' | 'bots_usd' | 'warn' | 'no_new_buys' | 'auto_sell'>
>;

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
