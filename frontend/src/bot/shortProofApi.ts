/**
 * The Live short proof (ADR 048 step 6, #778 §7): `GET /api/short-proof`, the operator's steps before a short may
 * go to Live, each ticked from what Nova sees. Checked on arrival: an unknown shape is an error, never a proof
 * that reads done.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { BOTS_PROOF_OLD_BACKEND } from '../constantGroups/bots_page';

export interface ProofStep {
  id: string;
  label: string;
  /** Done, not yet, or not known (null): never read as done. */
  ok: boolean | null;
  text: string;
  value: string | null;
  /** Who can tick it: Nova from what it sees, or only the operator. */
  seen: 'nova' | 'operator';
  /** The execution door refuses a Live short until it is done. */
  enforced: boolean;
  /** What to do, when it is not done. */
  how: string | null;
  at: number | null;
}

export interface ProofDay { date: string; shorts: number; symbols: string[] }

export interface ShortProofView {
  complete: boolean;
  missing: string | null;
  error: string | null;
  done: number;
  total: number;
  steps: ProofStep[];
  days: ProofDay[];
  review: { open: boolean; why: string };
}

const obj = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function parseStep(raw: unknown): ProofStep | null {
  const s = obj(raw);
  if (!s || !str(s.id) || !str(s.label)) return null;
  return {
    id: str(s.id) as string,
    label: str(s.label) as string,
    ok: s.ok === true ? true : s.ok === false ? false : null,
    text: str(s.text) ?? '',
    value: str(s.value),
    seen: s.seen === 'operator' ? 'operator' : 'nova',
    enforced: s.enforced === true,
    how: str(s.how),
    at: num(s.at),
  };
}

export function parseShortProof(raw: unknown): ShortProofView | null {
  const r = obj(raw);
  if (!r || r.schema_version !== 1 || !Array.isArray(r.steps)) return null;
  const steps = r.steps.map(parseStep);
  if (steps.some(s => s === null)) return null;
  const days: ProofDay[] = (Array.isArray(r.days) ? r.days : []).flatMap(d => {
    const day = obj(d);
    return day && str(day.date)
      ? [{ date: str(day.date) as string, shorts: num(day.shorts) ?? 0,
        symbols: Array.isArray(day.symbols) ? day.symbols.filter((x): x is string => typeof x === 'string') : [] }]
      : [];
  });
  const review = obj(r.review);
  return {
    complete: r.complete === true,
    missing: str(r.missing),
    error: str(r.error),
    done: num(r.done) ?? 0,
    total: num(r.total) ?? steps.length,
    steps: steps as ProofStep[],
    days,
    review: { open: review?.open === true, why: str(review?.why) ?? '' },
  };
}

export async function fetchShortProof(): Promise<ShortProofView> {
  const res = await novaFetch(`${API_BASE_URL}/api/short-proof`);
  if (res.status === 404) throw new Error(BOTS_PROOF_OLD_BACKEND);
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(`The Live short proof answered ${res.status}.`);
  const view = parseShortProof(body);
  if (!view) throw new Error('The Live short proof answered in a shape this desk does not read.');
  return view;
}
