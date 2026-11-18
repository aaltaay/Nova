/**
 * The brain on the wire (ADR 072, `architecture/schema/traders.md`): `GET /api/traders` read into the brain's one
 * shape, and the operator's one write -- the brain's On / Off switch, `PUT /api/traders/brain/switch {on}`, which
 * answers the same shape. The switch carries the desk's API key (`novaFetch`) and the sample desk refuses it before
 * any request. A refusal (a 409 when On is refused) is said in Nova's own words, never swallowed.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import type {
  BrainEvent, BrainHanded, BrainPosition, BrainReading, BrainSeatLane, BrainSeatStatus, BrainState,
} from './types';

export const TRADERS_PATH = '/api/traders';
export const BRAIN_SWITCH_PATH = '/api/traders/brain/switch';
export const BRAIN_SWITCH_NO_KEY = 'The desk has no API key for this: Nova needs NOVA_API_KEY to switch the brain.';

const STATES: readonly BrainState[] = ['off', 'watching', 'buy_set', 'in_trade', 'done'];

const obj = (v: unknown): Record<string, unknown> =>
  (v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const isObj = (v: unknown): boolean => v != null && typeof v === 'object' && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const sym = (v: unknown): string | null => str(v)?.toUpperCase() ?? null;
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const keep = <T,>(rows: unknown[], read: (raw: unknown) => T | null): T[] =>
  rows.map(read).filter((x): x is T => x !== null);

function lane(raw: unknown): BrainSeatLane {
  const r = obj(raw);
  return { symbol: sym(r.symbol), depth: r.depth === true, tape: r.tape === true, why: str(r.why) };
}

function position(raw: unknown): BrainPosition | null {
  const r = obj(raw);
  const symbol = sym(r.symbol);
  const qty = num(r.qty);
  if (!symbol || qty === null) return null;
  return { symbol, qty, avg_cost: num(r.avg_cost), mark: num(r.mark), unrealized_pnl: num(r.unrealized_pnl) };
}

function handed(raw: unknown): BrainHanded | null {
  const r = obj(raw);
  const symbol = sym(r.symbol);
  return symbol ? { symbol, qty: num(r.qty) ?? 0, stop_price: num(r.stop_price) } : null;
}

function reading(raw: unknown): BrainReading | null {
  const r = obj(raw);
  const symbol = sym(r.symbol);
  return symbol ? { symbol, text: str(r.text) ?? '', source: r.source === 'lane' ? 'lane' : 'level1' } : null;
}

function event(raw: unknown): BrainEvent | null {
  const r = obj(raw);
  const at = num(r.at);
  const text = str(r.text);
  return at === null || !text ? null : { at, kind: str(r.kind) ?? 'note', symbol: sym(r.symbol), text };
}

/**
 * The brain as this desk reads it; null for an answer that is not the traders view or carries no brain. A field
 * the answer lacks reads empty -- `connected` unknown (null) on a backend from before the brain's door -- and
 * nothing is invented.
 */
export function readBrainSeat(raw: unknown): BrainSeatStatus | null {
  const top = obj(raw);
  const traders = obj(top.traders);
  if (!isObj(traders.brain)) return null;
  const r = obj(traders.brain);
  const on = r.on === true;
  const state = STATES.find(s => s === r.state) ?? (on ? 'watching' : 'off');
  const why = obj(r.why_not_on);
  const whyError = str(why.error);
  const today = obj(r.today);
  const limits = obj(r.limits);
  const note = obj(r.note);
  const paused = obj(r.paused);
  const pausedVenue = str(paused.venue)?.toLowerCase();
  return {
    paused: pausedVenue ? { venue: pausedVenue, text: str(paused.text) ?? '' } : null,
    venue: str(top.venue)?.toLowerCase() ?? null,
    on, at: num(r.at), can_turn_on: r.can_turn_on === true,
    why_not_on: whyError ? { reason: str(why.reason) ?? '', error: whyError } : null,
    done_for_today: r.done_for_today === true, state, text: str(r.text) ?? 'Brain',
    symbol: sym(r.symbol), lane: lane(r.lane), position: position(r.position),
    handed: keep(list(r.handed), handed),
    today: { pnl: num(today.pnl), loss_limit_usd: num(today.loss_limit_usd), tripped_at: num(today.tripped_at) },
    limits: {
      max_shares: num(limits.max_shares), risk_usd: num(limits.risk_usd), budget_usd: num(limits.budget_usd),
      budget_used_usd: num(limits.budget_used_usd), flat_by: str(limits.flat_by),
    },
    note: str(note.text) ? { text: String(note.text), at: num(note.at) ?? 0 } : null,
    connected: typeof r.connected === 'boolean' ? r.connected : null,
    reading: keep(list(r.reading), reading),
    wakes: r.wakes === true,
    events: keep(list(r.events), event),
    read_error: str(top.error),
    generated_at: num(top.generated_at) ?? 0,
  };
}

/** The brain, or null while this backend has no traders view (404: an older backend). */
export async function fetchBrainSeat(signal?: AbortSignal): Promise<BrainSeatStatus | null> {
  const res = await novaFetch(`${API_BASE_URL}${TRADERS_PATH}`, { signal });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`The traders view answered ${res.status}.`);
  const view = readBrainSeat(await res.json());
  if (!view) throw new Error('The traders view answered in a shape this desk does not read.');
  return view;
}

/** The refusal's own words (`{detail: {reason, error}}`, or a plain `detail`), else what the desk answered. */
function refusal(status: number, answer: unknown): string {
  const top = obj(answer);
  return str(obj(top.detail).error) ?? str(top.detail) ?? str(top.error) ?? `The brain's switch answered ${status}.`;
}

/**
 * Switch the brain On or Off (ADR 072). Off hands the brain's open trade to you, untouched; On is refused after its
 * day stop, after its flat-by time, or on Live, in Nova's words. Resolves with the brain as the answer reads it, or
 * as the next read does when the answer carries no brain.
 */
export async function setBrainSwitch(on: boolean): Promise<BrainSeatStatus | null> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  const res = await novaFetch(`${API_BASE_URL}${BRAIN_SWITCH_PATH}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ on }),
  });
  const answer: unknown = await res.json().catch(() => null);
  if (res.status === 401 || res.status === 503) throw new Error(BRAIN_SWITCH_NO_KEY);
  if (!res.ok) throw new Error(refusal(res.status, answer));
  return readBrainSeat(answer) ?? fetchBrainSeat();
}
