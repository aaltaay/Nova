/**
 * Today's hot list over HTTP (ADR 043). The reads are plain; the writes change what Nova may trade, so
 * they carry the desk's API key (`novaFetch`) and the sample desk refuses them before any request. A
 * refusal throws the backend's own words.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { HOT_LIST_PATH } from './constants';
import type { HotEntry, HotListView, HotSide } from './types';

const side = (v: unknown): HotSide => (v === 'nova' ? 'nova' : 'you');
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null);

/** The wire, checked: an unknown shape is an error, never a guessed list. */
export function normalizeHotList(raw: unknown): HotListView | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (r.schema_version !== 1 || !Array.isArray(r.entries)) return null;
  const auto = (r.auto && typeof r.auto === 'object' ? r.auto : {}) as Record<string, unknown>;
  const dflt = (r.default && typeof r.default === 'object' ? r.default : {}) as Record<string, unknown>;
  const entries: HotEntry[] = [];
  for (const e of r.entries as unknown[]) {
    if (!e || typeof e !== 'object') continue;
    const x = e as Record<string, unknown>;
    const symbol = str(x.symbol)?.toUpperCase();
    if (!symbol) continue;
    entries.push({
      symbol,
      how: x.how === 'auto' ? 'auto' : 'star',
      at: num(x.at) ?? 0,
      board: str(x.board),
      rank: num(x.rank),
      change_pct: num(x.change_pct),
      followed: typeof x.followed === 'boolean' ? x.followed : null,
    });
  }
  return {
    schema_version: 1,
    date: str(r.date) ?? '',
    cap: num(r.cap) ?? 20,
    auto: {
      n: num(auto.n) ?? 0, start: str(auto.start) ?? '07:00', end: str(auto.end) ?? '16:00',
      rule: auto.rule && typeof auto.rule === 'object' ? auto.rule as Record<string, unknown> : null,
      error: str(auto.error),
    },
    default: { buy: side(dflt.buy), sell: side(dflt.sell) },
    entries,
    yesterday: Array.isArray(r.yesterday) ? (r.yesterday as unknown[]).filter((s): s is string => typeof s === 'string') : [],
    error: str(r.error),
  };
}

function refusal(status: number, body: unknown): string {
  const detail = body && typeof body === 'object' ? (body as { detail?: unknown }).detail : null;
  if (status === 401 || status === 503) return 'The desk has no API key for this: Nova needs NOVA_API_KEY to change the hot list.';
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (detail && typeof detail === 'object') {
    const error = (detail as { error?: unknown }).error;
    if (typeof error === 'string' && error.trim()) return error.trim();
  }
  if (status === 404) return 'This backend has no hot list yet: reload the backend after the update.';
  return `The desk answered ${status}.`;
}

async function call(method: 'GET' | 'POST' | 'DELETE' | 'PATCH', suffix = '', body?: unknown): Promise<HotListView> {
  if (method !== 'GET' && onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  const res = await novaFetch(`${API_BASE_URL}${HOT_LIST_PATH}${suffix}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const json: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(refusal(res.status, json));
  const view = normalizeHotList(json);
  if (!view) throw new Error('The hot list answered in a shape this desk does not read.');
  return view;
}

export const fetchHotList = () => call('GET');
export const starSymbol = (symbol: string) => call('POST', '/star', { symbol });
export const unstarSymbol = (symbol: string) => call('DELETE', `/${encodeURIComponent(symbol)}`);
export const patchHotList = (patch: { auto_n?: number; default_buy?: HotSide; default_sell?: HotSide }) => call('PATCH', '', patch);
export const bringBackYesterday = () => call('POST', '/bring-back');
