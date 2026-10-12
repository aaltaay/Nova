/**
 * Which target would have paid (#845, operator ask 2026-10-12): `GET /api/setups/target-choices`. Every trigger of a
 * setup since a date is scored once for each target choice -- a fixed 10c / 20c / 30c, the next level of today's
 * map, the pullback's high, the high of day (each selling everything there) and the template's own two targets -- so
 * the choices sit side by side on the same triggers. The backend ranks them by mean R net of a stated cost a share a
 * fill, and names no leader under its minimum count. R is the risk a share: the unit the scores are measured in.
 * Read-only; checked on arrival: an unknown shape is an error, never an empty table.
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { messageFromBotApiBody } from './botApiError';

export const TARGET_CHOICES_SCHEMA_VERSION = 1;

export interface TargetChoice {
  name: string;
  n: number;
  wins: number;
  win_pct: number | null;
  mean_r: number | null;
  sum_r: number | null;
  mean_net_r: number | null;
  sum_net_r: number | null;
  /** Triggers where the choice had no level and fell back to the fixed amount. */
  fell_back: number;
  /** Triggers not closed yet under this choice. */
  open: number;
}

export interface TargetChoices {
  from: string;
  setup_type: string;
  template: string | null;
  /** Dollars a share a fill the net columns take off. */
  cost: number;
  min_n: number;
  triggers: number;
  scored: number;
  /** Best first by mean net R. */
  choices: TargetChoice[];
  /** Null below the minimum count; `note` says why. */
  leader: string | null;
  note: string;
}

const obj = (v: unknown): Record<string, unknown> | null =>
  (v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);

function choice(raw: unknown): TargetChoice | null {
  const c = obj(raw);
  const n = num(c?.n);
  if (!c || typeof c.name !== 'string' || n === null) return null;
  return {
    name: c.name, n, wins: num(c.wins) ?? 0, win_pct: num(c.win_pct), mean_r: num(c.mean_r), sum_r: num(c.sum_r),
    mean_net_r: num(c.mean_net_r), sum_net_r: num(c.sum_net_r), fell_back: num(c.fell_back) ?? 0, open: num(c.open) ?? 0,
  };
}

/** The read-out off the wire; null when it is another schema or a choice cannot be read. */
export function parseTargetChoices(raw: unknown): TargetChoices | null {
  const r = obj(raw);
  const cost = num(r?.cost);
  if (!r || num(r.schema_version) !== TARGET_CHOICES_SCHEMA_VERSION || cost === null || !Array.isArray(r.choices)) return null;
  const choices = r.choices.map(choice);
  if (choices.some(c => c === null)) return null;
  return {
    from: str(r.from) ?? '', setup_type: str(r.setup_type) ?? '', template: str(r.template), cost,
    min_n: num(r.min_n) ?? 0, triggers: num(r.triggers) ?? 0, scored: num(r.scored) ?? 0,
    choices: choices as TargetChoice[], leader: str(r.leader), note: str(r.note) ?? '',
  };
}

export function targetChoicesUrl(from: string, setup: string): string {
  return `${API_URL}/setups/target-choices?from=${encodeURIComponent(from)}&setup=${encodeURIComponent(setup)}`;
}

export async function fetchTargetChoices(from: string, setup: string, signal?: AbortSignal): Promise<TargetChoices> {
  const res = await novaFetch(targetChoicesUrl(from, setup), { signal });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(messageFromBotApiBody(res.status, body ?? {}));
  const parsed = parseTargetChoices(body);
  if (!parsed) throw new Error('The target read-out answered in a shape this page cannot read');
  return parsed;
}

/** A choice in the menu's words: "+20c", "1c under the next level", "the template's two targets" (a short's mirror). */
export function choiceLabel(name: string, short = false): string {
  const fixed = /^fixed_(\d+)c$/.exec(name);
  if (fixed) return `${short ? '-' : '+'}${fixed[1]}c`;
  const words: Record<string, [string, string]> = {
    next_level: ['1c under the next level', '1c over the next level'],
    pullback_high: ['the pullback high', 'the bounce low'],
    hod: ['1c under HOD', '1c over LOD'],
    default: ["the template's two targets", "the template's two covers"],
  };
  return words[name]?.[short ? 1 : 0] ?? name.replace(/_/g, ' ');
}
