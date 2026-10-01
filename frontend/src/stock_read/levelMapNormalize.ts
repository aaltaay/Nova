/** Wire -> types for the day's levels (ADR 036 amendment 2026-09-30): the read's `level_map` and the
 * plan's `levels`. A field the wire lacks or mistypes is dropped or null -- never guessed; a map of
 * another schema version is null. */
import type {
  LevelKind,
  LevelMap,
  LevelMember,
  LevelRounds,
  LevelStudy,
  LevelZone,
  PlanBetween,
  PlanLevelNote,
  PlanLevels,
} from './levelTypes';
import type { ReadState } from './types';

export const LEVEL_MAP_SCHEMA_VERSION = 1;

const KINDS: ReadonlySet<string> = new Set<LevelKind>([
  'hod', 'lod', 'pmh', 'open', 'vwap', 'top', 'bottom', 'whole', 'half', 'yday_high', 'yday_low',
  'prior_close', 'daily_highs', 'daily_lows', 'daily_high', 'gap', 'sma200',
]);
const SIDES: ReadonlySet<string> = new Set(['above', 'below', 'at', 'unknown']);
const STATES: ReadonlySet<string> = new Set<ReadState>(['ok', 'warn', 'bad', 'unknown', 'info']);
const STUDY_KEYS = ['round_turn', 'round_through', 'round_lost', 'hod_past', 'top_past', 'daily_past'] as const;

// `normalize.ts` imports this file, so its helpers are repeated here rather than imported (as in planVerdict.ts).
type Obj = Record<string, unknown>;

function obj(v: unknown): Obj | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === 'string' ? v : null;
}

function list<T>(v: unknown, fn: (x: unknown) => T | null): T[] {
  return Array.isArray(v) ? v.map(fn).filter((x): x is T => x !== null) : [];
}

function member(raw: unknown): LevelMember | null {
  const m = obj(raw);
  const price = num(m?.price);
  if (!m || price === null || typeof m.kind !== 'string' || !KINDS.has(m.kind)) return null;
  return {
    kind: m.kind as LevelKind,
    price,
    label: str(m.label) ?? m.kind,
    touches: num(m.touches),
    times: list(m.times, num),
    dates: list(m.dates, str),
    note: str(m.note),
  };
}

function zone(raw: unknown): LevelZone | null {
  const z = obj(raw);
  const lo = num(z?.lo);
  const hi = num(z?.hi);
  const price = num(z?.price);
  if (!z || lo === null || hi === null || price === null || typeof z.id !== 'string') return null;
  const members = list(z.members, member);
  if (members.length === 0) return null;
  return {
    id: z.id,
    lo,
    hi,
    price,
    side: (typeof z.side === 'string' && SIDES.has(z.side) ? z.side : 'unknown') as LevelZone['side'],
    strength: num(z.strength) ?? 0,
    label: str(z.label) ?? '',
    tag: str(z.tag) ?? str(z.label) ?? '',
    home: z.home === 'daily' ? 'daily' : z.home === 'five_minute' ? 'five_minute' : 'intraday',
    members,
  };
}

function pair(v: unknown): [number, number] | null {
  if (!Array.isArray(v) || v.length !== 2) return null;
  const a = num(v[0]);
  const b = num(v[1]);
  return a === null || b === null ? null : [a, b];
}

function study(raw: unknown): LevelStudy | null {
  const s = obj(raw);
  if (!s) return null;
  const out: Partial<LevelStudy> = { source: str(s.source) ?? '' };
  for (const k of STUDY_KEYS) {
    const p = pair(s[k]);
    if (!p) return null;
    out[k] = p;
  }
  return out as LevelStudy;
}

function roundScale(raw: unknown): LevelRounds | null {
  const r = obj(raw);
  const minor = num(r?.minor);
  const major = num(r?.major);
  if (!r || minor === null || major === null || !(minor > 0) || typeof r.measured !== 'boolean') return null;
  return { minor, major, measured: r.measured, words: str(r.words) ?? 'round numbers' };
}

/** The read's level map; null when absent or of another schema version. */
export function normalizeLevelMap(raw: unknown): LevelMap | null {
  const m = obj(raw);
  if (!m || num(m.schema_version) !== LEVEL_MAP_SCHEMA_VERSION) return null;
  return {
    schema_version: LEVEL_MAP_SCHEMA_VERSION,
    price: num(m.price),
    rounds: roundScale(m.rounds),
    intraday: list(m.intraday, zone),
    five_minute: Array.isArray(m.five_minute) ? list(m.five_minute, zone) : null,
    daily: list(m.daily, zone),
    daily_sessions: num(m.daily_sessions) ?? 0,
    daily_error: str(m.daily_error),
    study: study(m.study),
  };
}

function note(raw: unknown): PlanLevelNote | null {
  const n = obj(raw);
  if (!n || typeof n.text !== 'string') return null;
  return {
    state: (typeof n.state === 'string' && STATES.has(n.state) ? n.state : 'unknown') as ReadState,
    text: n.text,
    detail: str(n.detail),
  };
}

function between(raw: unknown): PlanBetween | null {
  const b = obj(raw);
  const price = num(b?.price);
  if (!b || price === null) return null;
  return {
    price,
    lo: num(b.lo) ?? price,
    hi: num(b.hi) ?? price,
    tag: str(b.tag) ?? '',
    label: str(b.label) ?? str(b.tag) ?? '',
    round: b.round === true,
    hod: b.hod === true,
  };
}

/** The plan's level notes; null when the plan carries none. */
export function normalizePlanLevels(raw: unknown): PlanLevels | null {
  const l = obj(raw);
  const room = obj(l?.room);
  const roomNote = note(room);
  if (!l || !room || !roomNote) return null;
  return {
    room: { ...roomNote, r: num(room.r), price: num(room.price), trial: str(room.trial) ?? '' },
    target: note(l.target),
    stop: note(l.stop),
    next: note(l.next),
    recent: note(l.recent),
    between: list(l.between, between),
  };
}
