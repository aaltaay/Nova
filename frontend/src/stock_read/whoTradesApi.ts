/**
 * The writes behind the Who trades switch (ADR 037): set the switch, approve the plan, withdraw it, take
 * over the exit. They place and cancel orders, so they carry the desk's API key (`novaFetch`), and the
 * sample desk refuses them before any request. A refusal throws the backend's own words.
 *
 * The switch carries no risk per trade (ADR 042 draft): Nova sizes by the venue's sleeve, and the backend
 * ignores a `risk_usd` it is sent. A take-over sends nothing but the symbol: it always leaves Buy on You.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { STOCK_MODE_PATH } from './constants';
import type { StockModeView, StockPlan, StockSide } from './types';
import { normalizeStockMode } from './whoTradesNormalize';

/** The backend's refusal, in its own words: `{detail: {reason, error, field}}` or a plain detail.
 * `what` finishes "Nova needs NOVA_API_KEY to let the desk ..." when the desk has no key. */
export function refusalText(status: number, body: unknown, what = 'change who trades'): string {
  const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null;
  if (status === 401 || status === 503) {
    return `The desk has no API key for this: Nova needs NOVA_API_KEY to let the desk ${what}.`;
  }
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (detail && typeof detail === 'object') {
    const error = (detail as { error?: unknown }).error;
    if (typeof error === 'string' && error.trim()) return error.trim();
    const said = (detail as { detail?: unknown }).detail;
    if (typeof said === 'string' && said.trim()) return said.trim();
  }
  return `The desk answered ${status}.`;
}

async function send(symbol: string, method: 'PUT' | 'POST' | 'DELETE', suffix: string, body?: unknown): Promise<StockModeView> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  const url = `${API_BASE_URL}${STOCK_MODE_PATH}/${encodeURIComponent(symbol)}${suffix}`;
  const res = await novaFetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const json: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(refusalText(res.status, json));
  const view = normalizeStockMode(json);
  if (!view) throw new Error(`The desk's answer to ${method} ${STOCK_MODE_PATH} was not a stock's view.`);
  return view;
}

export function putStockMode(symbol: string, buy: StockSide, sell: StockSide): Promise<StockModeView> {
  return send(symbol, 'PUT', '', { buy, sell });
}

/** The plan Nova sends at the trigger. Two halves (#845): `target2` sells the rest after `target1_fraction` of the
 * shares sold at `target`; null sells every share at `target`. The backend binds both targets to the lane's. */
export interface ApproveBody {
  setup_id: string;
  entry: number;
  stop: number;
  target: number;
  target2: number | null;
  target1_fraction: number | null;
  qty: number;
  now: boolean;
}

/** The approval of a setup plan with what it sells (#845): both targets and the first half's share as the plan
 * reads them, so the bracket sells in the plan's two halves. The caller checks the plan has its levels. */
export function approveRequest(plan: StockPlan, qty: number, now: boolean): ApproveBody {
  const target2 = plan.target2 ?? null;
  return {
    setup_id: plan.setup_id as string,
    entry: plan.entry as number,
    stop: plan.stop as number,
    target: plan.target as number,
    target2,
    target1_fraction: target2 === null ? null : plan.target1_fraction ?? null,
    qty,
    now,
  };
}

export function approvePlan(symbol: string, body: ApproveBody): Promise<StockModeView> {
  return send(symbol, 'POST', '/approve', body);
}

export function withdrawApproval(symbol: string): Promise<StockModeView> {
  return send(symbol, 'DELETE', '/approve');
}

export function takeOverExit(symbol: string): Promise<StockModeView> {
  return send(symbol, 'POST', '/take-over');
}

/** Nova takes the exit of the shares you hold (ADR 037 amendment 2026-10-01): a resting stop, raised as
 * round numbers break when `trail`, and its targets beside it when the sheet chose them (#681: target 1 the
 * first half, target 2 the rest). Paper and Sim; the backend refuses Live. */
export function takeExit(symbol: string, body: {
  stop: number; trail: boolean; target?: number | null; target2?: number | null; target1_fraction?: number | null;
}): Promise<StockModeView> {
  return send(symbol, 'POST', '/take-exit', body);
}
