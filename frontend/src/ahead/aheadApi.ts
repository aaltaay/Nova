/**
 * Ahead's two reads (ADR 065, `architecture/schema/ahead.md`): `GET /api/ahead/forecast/{symbol}` and
 * `GET /api/ahead/status`. Every body passes a strict check here: a field that is missing or the wrong shape makes the
 * whole answer an `error` naming that field, and nothing is filled in. A non-ready answer that carries AI numbers is
 * refused the same way (a forecast the backend did not stand behind is never drawn).
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { AHEAD_HORIZON, AHEAD_LEVEL_EPS, AHEAD_LEVELS, AHEAD_STEP_SEC, AHEAD_WORDS } from './aheadConstants';
import type {
  AheadAi, AheadAiState, AheadAnswer, AheadExam, AheadLiveScore, AheadModel, AheadPaths, AheadScore, AheadStatus,
} from './aheadTypes';

/** One read: an answer, or words for why there is none (a 404 before the API restart, an unreachable API). */
export interface AheadFetch {
  answer: AheadAnswer | null;
  problem: string | null;
}

const STATES: readonly AheadAiState[] = [
  'ready', 'pending', 'not_set_up', 'offline', 'warming', 'not_enough_bars', 'quiet', 'error',
];
const VENUES = ['live', 'paper', 'sim'] as const;
const HEALTH_STATES = ['ready', 'warming', 'error'] as const;
const READY_ONLY = ['levels', 'close', 'volume', 'paths', 'volume_15', 'range_15', 'compute_ms', 'issued_at'] as const;

class Malformed extends Error {
  readonly field: string;

  constructor(field: string) {
    super(field);
    this.field = field;
  }
}

type Obj = Record<string, unknown>;

function obj(v: unknown, field: string): Obj {
  if (v === null || typeof v !== 'object' || Array.isArray(v)) throw new Malformed(field);
  return v as Obj;
}
function num(v: unknown, field: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new Malformed(field);
  return v;
}
function numOrNull(v: unknown, field: string): number | null {
  return v === null ? null : num(v, field);
}
function str(v: unknown, field: string): string {
  if (typeof v !== 'string') throw new Malformed(field);
  return v;
}
function strOrNull(v: unknown, field: string): string | null {
  return v === null ? null : str(v, field);
}
function bool(v: unknown, field: string): boolean {
  if (typeof v !== 'boolean') throw new Malformed(field);
  return v;
}
function oneOf<T extends string>(v: unknown, allowed: readonly T[], field: string): T {
  if (typeof v !== 'string' || !(allowed as readonly string[]).includes(v)) throw new Malformed(field);
  return v as T;
}

/** A row of finite numbers, non-decreasing, each passing `ok`. */
function row(v: unknown, len: number, field: string, ok: (x: number) => boolean): number[] {
  if (!Array.isArray(v) || v.length !== len) throw new Malformed(field);
  const out = v.map((x, i) => num(x, `${field}[${i}]`));
  for (let i = 0; i < out.length; i += 1) {
    if (!ok(out[i]) || (i > 0 && out[i] < out[i - 1])) throw new Malformed(field);
  }
  return out;
}
function rows(v: unknown, n: number, len: number, field: string, ok: (x: number) => boolean): number[][] {
  if (!Array.isArray(v) || v.length !== n) throw new Malformed(field);
  return v.map((r, i) => row(r, len, `${field}[${i}]`, ok));
}

const positive = (x: number) => x > 0;
const nonNegative = (x: number) => x >= 0;

function model(v: unknown, field: string): AheadModel | null {
  if (v === null) return null;
  const m = obj(v, field);
  return { name: str(m.name, `${field}.name`), version: str(m.version, `${field}.version`) };
}

function score(v: unknown, field: string): AheadScore {
  const s = obj(v, field);
  return { spearman: num(s.spearman, `${field}.spearman`), miss_x: num(s.miss_x, `${field}.miss_x`) };
}

function versus(v: unknown, field: string): AheadExam['volume'] {
  const p = obj(v, field);
  const b = obj(p.baseline, `${field}.baseline`);
  return { model: score(p.model, `${field}.model`), baseline: { ...score(b, `${field}.baseline`), name: str(b.name, `${field}.baseline.name`) } };
}

export function normalizeExam(v: unknown, field: string): AheadExam | null {
  if (v === null) return null;
  const e = obj(v, field);
  const sample = obj(e.sample, `${field}.sample`);
  return {
    passed: bool(e.passed, `${field}.passed`),
    as_of: str(e.as_of, `${field}.as_of`),
    summary: str(e.summary, `${field}.summary`),
    // A forecaster that does not say what its exam covered: a stated null, never a guess.
    scope: e.scope === undefined ? null : strOrNull(e.scope, `${field}.scope`),
    volume: versus(e.volume, `${field}.volume`),
    range: versus(e.range, `${field}.range`),
    band80_coverage: num(e.band80_coverage, `${field}.band80_coverage`),
    sample: { days: num(sample.days, `${field}.sample.days`), moments: num(sample.moments, `${field}.sample.moments`) },
  };
}

function levels(v: unknown): number[] {
  if (!Array.isArray(v) || v.length !== AHEAD_LEVELS.length) throw new Malformed('ai.levels');
  v.forEach((x, i) => {
    if (typeof x !== 'number' || Math.abs(x - AHEAD_LEVELS[i]) > AHEAD_LEVEL_EPS) throw new Malformed('ai.levels');
  });
  return [...AHEAD_LEVELS];
}

function paths(v: unknown, horizon: number): AheadPaths {
  const p = obj(v, 'ai.paths');
  const n = num(p.n, 'ai.paths.n');
  if (!Number.isInteger(n) || n < 16) throw new Malformed('ai.paths.n');
  if (!Array.isArray(p.close) || p.close.length !== n) throw new Malformed('ai.paths.close');
  const close = p.close.map((r, i) => {
    if (!Array.isArray(r) || r.length !== horizon) throw new Malformed(`ai.paths.close[${i}]`);
    return r.map((x, k) => {
      const c = num(x, `ai.paths.close[${i}][${k}]`);
      if (c <= 0) throw new Malformed(`ai.paths.close[${i}][${k}]`);
      return c;
    });
  });
  return { n, close, joined_by: str(p.joined_by, 'ai.paths.joined_by') };
}

function ai(v: unknown): AheadAi {
  const a = obj(v, 'ai');
  const state = oneOf(a.state, STATES, 'ai.state');
  const horizon = num(a.horizon_min, 'ai.horizon_min');
  if (horizon !== AHEAD_HORIZON) throw new Malformed('ai.horizon_min');
  if (num(a.step_sec, 'ai.step_sec') !== AHEAD_STEP_SEC) throw new Malformed('ai.step_sec');
  const base = {
    state,
    reason: strOrNull(a.reason, 'ai.reason'),
    need: numOrNull(a.need, 'ai.need'),
    have: numOrNull(a.have, 'ai.have'),
    retry_ms: numOrNull(a.retry_ms, 'ai.retry_ms'),
    retry_at: numOrNull(a.retry_at, 'ai.retry_at'),
    model: model(a.model, 'ai.model'),
    exam: normalizeExam(a.exam, 'ai.exam'),
    horizon_min: horizon,
    step_sec: AHEAD_STEP_SEC,
  };
  if (state !== 'ready') {
    for (const k of READY_ONLY) if (a[k] !== null) throw new Malformed(`ai.${k}`);
    if (a.exam_passed !== null) throw new Malformed('ai.exam_passed');
    return {
      ...base, exam_passed: null, levels: null, close: null, volume: null, paths: null, volume_15: null,
      range_15: null, compute_ms: null, issued_at: null,
    };
  }
  const width = AHEAD_LEVELS.length;
  return {
    ...base,
    exam_passed: bool(a.exam_passed, 'ai.exam_passed'),
    levels: levels(a.levels),
    close: rows(a.close, horizon, width, 'ai.close', positive),
    volume: rows(a.volume, horizon, width, 'ai.volume', nonNegative),
    paths: paths(a.paths, horizon),
    volume_15: row(a.volume_15, width, 'ai.volume_15', nonNegative),
    range_15: row(a.range_15, width, 'ai.range_15', nonNegative),
    compute_ms: numOrNull(a.compute_ms, 'ai.compute_ms'),
    issued_at: numOrNull(a.issued_at, 'ai.issued_at'),
  };
}

function answerOf(raw: unknown): AheadAnswer {
  const r = obj(raw, 'the body');
  if (r.schema_version !== 1) throw new Malformed('schema_version');
  const bars = obj(r.bars, 'bars');
  const bar_t = numOrNull(r.bar_t, 'bar_t');
  const as_of = numOrNull(r.as_of, 'as_of');
  const generated_at = num(r.generated_at, 'generated_at');
  // The backend's own rule: the forecast starts where the newest candle ends, never after the desk clock.
  if ((bar_t === null) !== (as_of === null) || (bar_t !== null && as_of !== bar_t + AHEAD_STEP_SEC)) {
    throw new Malformed('as_of');
  }
  if (as_of !== null && generated_at < as_of) throw new Malformed('generated_at');
  return {
    schema_version: 1,
    symbol: str(r.symbol, 'symbol'),
    generated_at,
    replay: bool(r.replay, 'replay'),
    venue: oneOf(r.venue, VENUES, 'venue'),
    bar_t,
    as_of,
    bars: {
      n: num(bars.n, 'bars.n'),
      contiguous_tail: num(bars.contiguous_tail, 'bars.contiguous_tail'),
      tail_gap_sec: numOrNull(bars.tail_gap_sec, 'bars.tail_gap_sec'),
    },
    price: numOrNull(r.price, 'price'),
    prior_close: numOrNull(r.prior_close, 'prior_close'),
    volume_last15: numOrNull(r.volume_last15, 'volume_last15'),
    ai: ai(r.ai),
    never: str(r.never, 'never'),
  };
}

/** An `error` answer for a body the desk cannot read: it names the field and carries no number at all. */
export function errorAnswer(symbol: string, reason: string): AheadAnswer {
  return {
    schema_version: 1, symbol, generated_at: 0, replay: false, venue: 'live', bar_t: null, as_of: null,
    bars: { n: 0, contiguous_tail: 0, tail_gap_sec: null }, price: null, prior_close: null, volume_last15: null,
    ai: {
      state: 'error', reason, need: null, have: null, retry_ms: null, retry_at: null, model: null, exam_passed: null,
      exam: null, horizon_min: AHEAD_HORIZON, step_sec: AHEAD_STEP_SEC, levels: null, close: null, volume: null,
      paths: null, volume_15: null, range_15: null, compute_ms: null, issued_at: null,
    },
    never: '',
  };
}

/** Strict: the wire answer, or an `error` answer naming the first field that is wrong. */
export function normalizeAnswer(raw: unknown, symbol: string): AheadAnswer {
  try {
    const a = answerOf(raw);
    if (a.symbol.toUpperCase() !== symbol.toUpperCase()) throw new Malformed('symbol');
    return a;
  } catch (err) {
    if (err instanceof Malformed) return errorAnswer(symbol, AHEAD_WORDS.malformed(err.field));
    throw err;
  }
}

function liveScore(v: unknown): AheadLiveScore {
  const l = obj(v, 'health.live');
  return {
    since: strOrNull(l.since, 'health.live.since'),
    scored: num(l.scored, 'health.live.scored'),
    volume_spearman: numOrNull(l.volume_spearman, 'health.live.volume_spearman'),
    range_spearman: numOrNull(l.range_spearman, 'health.live.range_spearman'),
    band80_coverage: numOrNull(l.band80_coverage, 'health.live.band80_coverage'),
  };
}

function statusOf(raw: unknown): AheadStatus {
  const r = obj(raw, 'the body');
  if (r.schema_version !== 1) throw new Malformed('schema_version');
  let health: AheadStatus['health'] = null;
  if (r.health !== null) {
    const h = obj(r.health, 'health');
    health = {
      state: oneOf(h.state, HEALTH_STATES, 'health.state'),
      detail: strOrNull(h.detail, 'health.detail'),
      contract_ok: bool(h.contract_ok, 'health.contract_ok'),
      model: model(h.model, 'health.model'),
      exam: normalizeExam(h.exam, 'health.exam'),
      live: liveScore(h.live),
    };
  }
  return {
    schema_version: 1,
    configured: bool(r.configured, 'configured'),
    reason: strOrNull(r.reason, 'reason'),
    checked_at: num(r.checked_at, 'checked_at'),
    health,
  };
}

/** Strict: the status, or `{ problem }` naming the field. */
export function normalizeStatus(raw: unknown): AheadStatus | { problem: string } {
  try {
    return statusOf(raw);
  } catch (err) {
    if (err instanceof Malformed) return { problem: AHEAD_WORDS.malformed(err.field) };
    throw err;
  }
}

async function readJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch (err) {
    console.warn('Ahead: an answer that is not JSON', err);
    return undefined;
  }
}

function transportProblem(err: unknown, signal: AbortSignal): string | null {
  if (signal.aborted) return null;
  console.warn('Ahead: Nova API request failed', err);
  return AHEAD_WORDS.apiUnreachable;
}

/** One forecast read. Rejects only when aborted (the caller dropped it); every other failure is words. */
export async function fetchAhead(symbol: string, signal: AbortSignal): Promise<AheadFetch> {
  let res: Response;
  try {
    res = await novaFetch(`${API_BASE_URL}/api/ahead/forecast/${encodeURIComponent(symbol)}`, { signal });
  } catch (err) {
    const problem = transportProblem(err, signal);
    if (problem === null) throw err;
    return { answer: null, problem };
  }
  if (res.status === 404) return { answer: null, problem: AHEAD_WORDS.apiMissing };
  if (!res.ok) return { answer: null, problem: AHEAD_WORDS.apiStatus(res.status) };
  return { answer: normalizeAnswer(await readJson(res), symbol), problem: null };
}

/** The forecaster's status; `problem` words instead when it cannot be read. */
export async function fetchAheadStatus(signal: AbortSignal): Promise<{ status: AheadStatus | null; problem: string | null }> {
  let res: Response;
  try {
    res = await novaFetch(`${API_BASE_URL}/api/ahead/status`, { signal });
  } catch (err) {
    const problem = transportProblem(err, signal);
    if (problem === null) throw err;
    return { status: null, problem };
  }
  if (res.status === 404) return { status: null, problem: AHEAD_WORDS.apiMissing };
  if (!res.ok) return { status: null, problem: AHEAD_WORDS.apiStatus(res.status) };
  const s = normalizeStatus(await readJson(res));
  return 'problem' in s ? { status: null, problem: s.problem } : { status: s, problem: null };
}
