/**
 * Claude's seat on the wire (ADR 068): `GET /api/agent/trader` read into one shape, and the operator's three
 * buttons -- take Claude's line, give it back, stop Claude. The buttons carry the desk's API key (`novaFetch`)
 * and the sample desk refuses them before any request. A refusal is said in words, never swallowed.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import type {
  ClaudeBreak, ClaudeEvent, ClaudeLine, ClaudeOrder, ClaudeReflex, ClaudeSeatState, ClaudeSeatStatus,
} from './types';

export const CLAUDE_SEAT_PATH = '/api/agent/trader';

const STATES: readonly ClaudeSeatState[] = [
  'off', 'idle', 'waiting_line', 'watching', 'buy_set', 'in_trade', 'yielded', 'done',
];

const obj = (v: unknown): Record<string, unknown> =>
  (v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

function order(raw: unknown): ClaudeOrder | null {
  const r = obj(raw);
  const id = num(r.order_id);
  const symbol = str(r.symbol);
  if (id === null || !symbol) return null;
  const role = str(r.leg_role);
  return {
    order_id: id, symbol: symbol.toUpperCase(), side: (str(r.side) ?? '').toUpperCase(), order_type: str(r.order_type),
    qty: num(r.qty) ?? 0, limit_price: num(r.limit_price), stop_price: num(r.stop_price),
    leg_role: role === 'parent' || role === 'target' || role === 'target2' || role === 'stop' ? role : null,
    status: str(r.status), parent_id: num(r.parent_id),
  };
}

function brk(raw: unknown): ClaudeBreak | null {
  const r = obj(raw);
  const id = str(r.id);
  const symbol = str(r.symbol);
  const trigger = num(r.trigger);
  const top = num(r.top);
  const stop = num(r.stop);
  const target = num(r.target);
  if (!id || !symbol || trigger === null || top === null || stop === null || target === null) return null;
  return {
    id, symbol: symbol.toUpperCase(), qty: num(r.qty) ?? 0, trigger, top, stop, target,
    target2: num(r.target2), target1_qty: num(r.target1_qty), expires_at: num(r.expires_at) ?? 0,
    created_at: num(r.created_at) ?? 0, why: str(r.why),
  };
}

function reflex(raw: unknown): ClaudeReflex | null {
  const r = obj(raw);
  const id = str(r.id);
  if (!id) return null;
  return {
    id, symbol: (str(r.symbol) ?? '').toUpperCase(), kind: str(r.kind) ?? '', action: str(r.action) ?? '',
    why: str(r.why), text: str(r.text) ?? str(r.why) ?? str(r.kind) ?? '', expires_at: num(r.expires_at),
  };
}

function event(raw: unknown): ClaudeEvent | null {
  const r = obj(raw);
  const at = num(r.at);
  const text = str(r.text);
  return at === null || !text ? null : { at, kind: str(r.kind) ?? 'note', text };
}

function line(raw: unknown): ClaudeLine {
  const r = obj(raw);
  const names = (v: unknown) => list(v).filter((s): s is string => typeof s === 'string').map(s => s.toUpperCase());
  return {
    symbol: str(r.symbol)?.toUpperCase() ?? null, depth: r.depth === true, tape: r.tape === true,
    why_not: str(r.why_not), desk_lines: names(r.desk_lines), desk_cap: num(r.desk_cap), all_lines: names(r.all_lines),
  };
}

const keep = <T,>(rows: unknown[], read: (raw: unknown) => T | null): T[] =>
  rows.map(read).filter((x): x is T => x !== null);

/** The status as this desk reads it; null for a shape it cannot read. */
export function readClaudeSeat(raw: unknown): ClaudeSeatStatus | null {
  const r = obj(raw);
  const state = str(r.state) as ClaudeSeatState | null;
  if (!state || !STATES.includes(state)) return null;
  const today = obj(r.today);
  const limits = obj(r.limits);
  const note = obj(r.note);
  return {
    state, text: str(r.text) ?? 'Claude', on: r.on === true, since: num(r.since), beat_at: num(r.beat_at),
    lease_until: num(r.lease_until), lapsed: r.lapsed === true, yielded: r.yielded === true,
    symbol: str(r.symbol)?.toUpperCase() ?? null, line: line(r.line),
    positions: list(r.positions).map(obj).filter(p => str(p.symbol)).map(p => ({
      symbol: String(p.symbol).toUpperCase(), qty: num(p.qty) ?? 0, mark: num(p.mark),
    })),
    working: keep(list(r.working), order),
    breaks: keep(list(r.breaks), brk),
    reflexes: keep(list(r.reflexes), reflex),
    today: {
      entries: num(today.entries) ?? 0, max_entries: num(today.max_entries), pnl: num(today.pnl),
      day_stop: num(today.day_stop), fills: num(today.fills) ?? 0,
    },
    limits: { max_shares: num(limits.max_shares), max_risk_usd: num(limits.max_risk_usd) },
    note: str(note.text) ? { text: String(note.text), at: num(note.at) ?? 0 } : null,
    events: keep(list(r.events), event),
    read_error: str(r.read_error),
    generated_at: num(r.generated_at) ?? 0,
  };
}

/** The seat's status, or null while this backend has no seat (404: an older backend). */
export async function fetchClaudeSeat(signal?: AbortSignal): Promise<ClaudeSeatStatus | null> {
  const res = await novaFetch(`${API_BASE_URL}${CLAUDE_SEAT_PATH}`, { signal });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Claude's seat answered ${res.status}.`);
  const view = readClaudeSeat(await res.json());
  if (!view) throw new Error("Claude's seat answered in a shape this desk does not read.");
  return view;
}

async function press(path: string): Promise<ClaudeSeatStatus | null> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  const res = await novaFetch(`${API_BASE_URL}${CLAUDE_SEAT_PATH}${path}`, { method: 'POST' });
  const body: unknown = await res.json().catch(() => null);
  if (res.status === 401 || res.status === 503) {
    throw new Error("The desk has no API key for this: Nova needs NOVA_API_KEY to change Claude's seat.");
  }
  if (!res.ok) {
    const detail = obj(obj(body).detail);
    throw new Error(str(detail.error) ?? `Claude's seat answered ${res.status}.`);
  }
  const b = obj(body);
  return readClaudeSeat('status' in b ? b.status : body);
}

/** Take Claude's line: Claude makes no new trades; an open trade keeps its stop. */
export const takeClaudesLine = () => press('/yield');
/** Give Claude its line back. */
export const giveClaudeLineBack = () => press('/give-back');
/** Stop Claude: its orders cancelled, its shares sold, the seat off, the line yours. */
export const stopClaude = () => press('/stop-claude');
