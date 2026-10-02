/**
 * The squares, by ticker (ADR 044): `GET /api/bot/triggers`. Every listed ticker's answer now, and every
 * trigger of the day on it, judged by the same ten checks in Nova's order. Checked on arrival: an unknown
 * shape is an error, never an empty table.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';

export type CellOk = boolean | null;
export interface Cell { ok: CellOk; why: string }
export type Cells = Record<string, Cell>;

export interface TickerTrigger {
  ts: number;
  setup_id: string | null;
  setup_type: string;
  kind: string | null;
  nth: number | null;
  grade: string | null;
  tape: string | null;
  outcome: string | null;
  r: number | null;
  cells: Cells;
  reasons: string[];
}

export interface TickerRow {
  symbol: string;
  listed: { how: 'auto' | 'star'; at: number } | null;
  now: { cells: Cells; answer: 'yes' | 'no'; reasons: string[] } | null;
  triggers: TickerTrigger[];
}

export interface GateImpact { gate: string; blocked: number; target_first: number; stop_first: number; r: number }

export interface TriggersView {
  date: string;
  gates: { id: string; label: string }[];
  tickers: TickerRow[];
  impact: GateImpact[];
  judgedNow: string[];
  sources: Record<string, { ok: boolean; error: string | null }>;
}

const obj = (v: unknown): Record<string, unknown> | null =>
  (v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);

function cells(v: unknown): Cells {
  const out: Cells = {};
  const o = obj(v);
  if (!o) return out;
  for (const [k, raw] of Object.entries(o)) {
    const c = obj(raw);
    if (!c) continue;
    out[k] = { ok: typeof c.ok === 'boolean' ? c.ok : null, why: str(c.why) ?? '' };
  }
  return out;
}

export function parseTriggers(raw: unknown): TriggersView | null {
  const r = obj(raw);
  if (!r || r.schema_version !== 1 || !Array.isArray(r.gates) || !Array.isArray(r.tickers)) return null;
  const gates = (r.gates as unknown[]).map(obj).filter(Boolean).map(g => ({ id: str(g!.id) ?? '', label: str(g!.label) ?? '' }))
    .filter(g => g.id);
  const tickers: TickerRow[] = [];
  for (const t of r.tickers as unknown[]) {
    const o = obj(t);
    const symbol = str(o?.symbol)?.toUpperCase();
    if (!o || !symbol) continue;
    const listed = obj(o.listed);
    const now = obj(o.now);
    tickers.push({
      symbol,
      listed: listed ? { how: listed.how === 'auto' ? 'auto' : 'star', at: num(listed.at) ?? 0 } : null,
      now: now ? { cells: cells(now.cells), answer: now.answer === 'yes' ? 'yes' : 'no', reasons: strs(now.reasons) } : null,
      triggers: (Array.isArray(o.triggers) ? o.triggers : []).map(obj).filter(Boolean).map(x => ({
        ts: num(x!.ts) ?? 0, setup_id: str(x!.setup_id), setup_type: str(x!.setup_type) ?? '', kind: str(x!.kind),
        nth: num(x!.nth), grade: str(x!.grade), tape: str(x!.tape), outcome: str(x!.outcome), r: num(x!.r),
        cells: cells(x!.cells), reasons: strs(x!.reasons),
      })),
    });
  }
  const impact = (Array.isArray(r.impact) ? r.impact : []).map(obj).filter(Boolean).map(i => ({
    gate: str(i!.gate) ?? '', blocked: num(i!.blocked) ?? 0, target_first: num(i!.target_first) ?? 0,
    stop_first: num(i!.stop_first) ?? 0, r: num(i!.r) ?? 0,
  }));
  const sources: TriggersView['sources'] = {};
  for (const [k, v] of Object.entries(obj(r.sources) ?? {})) {
    const s = obj(v);
    if (s) sources[k] = { ok: s.ok === true, error: str(s.error) };
  }
  return { date: str(r.date) ?? '', gates, tickers, impact, judgedNow: strs(r.judged_now), sources };
}

export async function fetchTriggers(date?: string): Promise<TriggersView> {
  const q = date ? `?date=${encodeURIComponent(date)}` : '';
  const res = await novaFetch(`${API_BASE_URL}/api/bot/triggers${q}`);
  if (res.status === 404) throw new Error('This backend has no triggers table yet: reload the backend after the update.');
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(`The triggers table answered ${res.status}.`);
  const view = parseTriggers(body);
  if (!view) throw new Error('The triggers table answered in a shape this desk does not read.');
  return view;
}
