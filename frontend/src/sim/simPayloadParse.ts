/**
 * Boundary parsers for the Sim clock, historical replay status and snapshot
 * (QA 2026-09-22, C6 / C7 / C9). Each takes the raw JSON body and returns the
 * shape the views are typed against, or throws when the body is not an object
 * at all -- the poll resource then reports it as a failed poll. Field-level
 * damage never throws: a bad field is dropped (read as absent), a bad row is
 * skipped, and the views state the absence instead of crashing the desk.
 */
import type { DepthLevel } from '../ibkr/types';
import type { HistoricalDepthBook, HistoricalJob, HistoricalSelection, HistoricalStatus } from './historicalTypes';
import type { CaptureSegment, SimClockState } from './simClockTypes';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import {
  compact, finite, finiteOrNull, flag, isObject, objects, rangePairs, text, textOrNull, type Obj,
} from './payloadGuards';

export const unreadable = (what: string): string => `Nova returned an unreadable ${what}. Try again.`;

/** `null` stays null (an explicit absence); any other non-string is dropped. */
const nullableText = (value: unknown): string | null | undefined => (value === null ? null : text(value));

function parseCounts(value: unknown): Record<string, number> | undefined {
  if (!isObject(value)) return undefined;
  const out: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value)) {
    const n = finite(raw);
    if (n != null) out[key] = n;
  }
  return out;
}

/** Manifest segments: a list of objects with a string start; a malformed stop drops the segment. */
export function parseSegments(value: unknown): CaptureSegment[] | undefined {
  if (value === undefined) return undefined;
  return objects(value)
    .map((segment): Obj => compact({
      ...segment,
      started_et: text(segment.started_et),
      stopped_et: segment.stopped_et == null ? null : text(segment.stopped_et),
      status: text(segment.status),
      reason: nullableText(segment.reason),
      counts: parseCounts(segment.counts),
    }))
    .filter(segment => typeof segment.started_et === 'string' && segment.stopped_et !== undefined)
    .map(segment => segment as unknown as CaptureSegment);
}

function parseReplayLoad(value: unknown): SimClockState['replay_load'] {
  if (!isObject(value)) return undefined;
  return compact({
    ...value,
    l2_total: finite(value.l2_total),
    l2_loaded: finite(value.l2_loaded),
    l2_decimated: flag(value.l2_decimated),
    malformed_rows: finite(value.malformed_rows),
    invalid_timestamp_rows: finite(value.invalid_timestamp_rows),
    invalid_rows: finite(value.invalid_rows),
    legacy_schema: flag(value.legacy_schema),
    segments: parseSegments(value.segments),
  }) as SimClockState['replay_load'];
}

/** `GET/POST /api/sim/clock` and `POST /api/sim/replay`. */
export function parseSimClock(raw: unknown): SimClockState {
  if (!isObject(raw)) throw new Error(unreadable('Sim clock'));
  return compact({
    ...raw,
    sim: raw.sim === true,
    sim_time_et: text(raw.sim_time_et),
    session_date: text(raw.session_date),
    session_open_et: text(raw.session_open_et),
    session_close_et: text(raw.session_close_et),
    phase: text(raw.phase),
    minute_from_open: finite(raw.minute_from_open),
    minute_max: finite(raw.minute_max),
    scrubbed: flag(raw.scrubbed),
    paused: flag(raw.paused),
    live_edge: flag(raw.live_edge),
    replay_date: nullableText(raw.replay_date),
    replay_symbol: nullableText(raw.replay_symbol),
    replay_source: text(raw.replay_source),
    replay_ok: raw.replay_ok === null ? null : flag(raw.replay_ok),
    replay_loading: flag(raw.replay_loading),
    replay_error: nullableText(raw.replay_error),
    replay_load: parseReplayLoad(raw.replay_load),
  }) as SimClockState;
}

function windowFields(value: Obj) {
  return {
    symbol: text(value.symbol) ?? '',
    date: text(value.date) ?? '',
    start: text(value.start) ?? '',
    end: text(value.end) ?? '',
  };
}

export function parseHistoricalSelection(value: Obj): HistoricalSelection {
  const start = finite(value.start_ts);
  return compact({
    ...value,
    ...windowFields(value),
    start_ts: start,
    end_ts: finite(value.end_ts),
    // Nothing contiguous downloaded reads as "through the window start".
    coverage_through: finite(value.coverage_through) ?? start ?? 0,
    coverage: rangePairs(value.coverage),
    covered_seconds: finite(value.covered_seconds),
    trade_count: finite(value.trade_count),
    download_status: text(value.download_status),
    job_id: nullableText(value.job_id),
  }) as HistoricalSelection;
}

function parseJob(value: Obj): HistoricalJob {
  return compact({
    ...value,
    ...windowFields(value),
    id: text(value.id) ?? '',
    kind: text(value.kind) ?? '',
    status: text(value.status) ?? '',
    count: finiteOrNull(value.count),
    pages: finiteOrNull(value.pages),
    error: textOrNull(value.error),
    cursor: finite(value.cursor),
    start_ts: finite(value.start_ts),
    end_ts: finite(value.end_ts),
    volume: finite(value.volume),
    updated: finite(value.updated),
    progress_pct: finite(value.progress_pct),
    downloaded_through: finite(value.downloaded_through),
    eta_seconds: finiteOrNull(value.eta_seconds),
    stale: flag(value.stale),
    age_seconds: finite(value.age_seconds),
    started: finite(value.started),
    coverage: rangePairs(value.coverage),
    covered_seconds: finite(value.covered_seconds),
  }) as HistoricalJob;
}

/** `GET /api/sim/history`. */
export function parseHistoricalStatus(raw: unknown): HistoricalStatus {
  if (!isObject(raw)) throw new Error(unreadable('historical replay status'));
  const selection = raw.selection === undefined ? undefined
    : isObject(raw.selection) ? parseHistoricalSelection(raw.selection) : null;
  return compact({
    ...raw,
    jobs: objects(raw.jobs).map(parseJob).filter(job => job.id),
    selection,
    default_date: text(raw.default_date),
  }) as HistoricalStatus;
}

function parseLevels(value: unknown, side: 'bid' | 'ask'): DepthLevel[] {
  return objects(value)
    .filter(level => finite(level.price) != null && finite(level.size) != null)
    .map(level => ({ ...level, price: level.price as number, size: level.size as number, side }) as DepthLevel);
}

function parseDepth(value: unknown): HistoricalDepthBook | null {
  if (!isObject(value)) return null;
  const ts = finite(value.ts);
  if (ts == null) return null;
  return {
    ...value,
    symbol: text(value.symbol) ?? '',
    bids: parseLevels(value.bids, 'bid'),
    asks: parseLevels(value.asks, 'ask'),
    ts,
    age_sec: finite(value.age_sec) ?? 0,
    l1_fallback: value.l1_fallback === true,
    session_id: textOrNull(value.session_id),
    source: text(value.source) ?? '',
  };
}

const SIDES = new Set(['ask', 'bid', 'between']);

function parsePrint(value: Obj): HistoricalSnapshot['prints'][number] | null {
  const time = text(value.time);
  const price = finite(value.price);
  const size = finite(value.size);
  if (!time || price == null || size == null) return null;
  const side = typeof value.side === 'string' && SIDES.has(value.side) ? value.side as 'ask' | 'bid' | 'between' : null;
  return compact({
    ...value,
    time,
    price,
    size,
    exchange: text(value.exchange) ?? '',
    conditions: text(value.conditions),
    unreported: value.unreported === true,
    ordinal: finite(value.ordinal),
    side,
    bid: finiteOrNull(value.bid),
    ask: finiteOrNull(value.ask),
    side_source: textOrNull(value.side_source),
  }) as HistoricalSnapshot['prints'][number];
}

/** `GET /api/sim/history/snapshot/{symbol}`. */
export function parseHistoricalSnapshot(raw: unknown): HistoricalSnapshot {
  if (!isObject(raw)) throw new Error(unreadable('historical replay snapshot'));
  return compact({
    ...raw,
    active: raw.active === true,
    symbol: text(raw.symbol) ?? '',
    last: finiteOrNull(raw.last),
    volume: finiteOrNull(raw.volume),
    source: text(raw.source) ?? '',
    as_of: text(raw.as_of) ?? '',
    error: text(raw.error),
    depth_available: flag(raw.depth_available),
    depth: parseDepth(raw.depth),
    open: finiteOrNull(raw.open),
    high: finiteOrNull(raw.high),
    low: finiteOrNull(raw.low),
    prev_close: finiteOrNull(raw.prev_close),
    selection: isObject(raw.selection) ? parseHistoricalSelection(raw.selection) : undefined,
    covered: flag(raw.covered),
    sides_recorded: finite(raw.sides_recorded),
    prints: objects(raw.prints).map(parsePrint).filter((p): p is NonNullable<typeof p> => p != null),
  }) as HistoricalSnapshot;
}
