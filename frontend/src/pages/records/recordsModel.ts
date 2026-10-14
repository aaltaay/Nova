/**
 * Records › Market data, pure (operator ask 2026-10-14): the coverage clock,
 * who ended each recording, its gaps, and each day's totals -- all read from
 * `/api/capture/sessions` and `/api/ibkr/status`, never guessed. A gap is
 * "missing" or "stopped on purpose" only because the listing names the reason
 * that ended the stretch before it; a listing without `gaps` draws none.
 * Schema: architecture/schema/recording-and-replay.md, "The Records page".
 */
import { JOURNAL_CALENDAR_TIMEZONE } from '../../constants';
import { recordingUnavailableReason, recordStatusWords } from '../../sim/captureRowFormat';
import type { CaptureSessionRow } from '../../sim/useSimSessionController';
import {
  RECORDS_ENDED_LIVE,
  RECORDS_ENDED_RESUMED,
  RECORDS_ENDED_STATUS,
  RECORDS_ENDED_STOPPED,
  RECORDS_PLANNED_STOP_REASONS,
} from './recordsConstants';

/** The coverage clock: minutes after midnight ET. */
export interface Axis {
  t0: number;
  t1: number;
}

export const AXIS_DEFAULT: Axis = { t0: 7 * 60, t1: 16 * 60 };
const AXIS_MIN = 4 * 60;
const AXIS_MAX = 20 * 60;
export const MARKET_OPEN_MIN = 9 * 60 + 30;
export const MARKET_CLOSE_MIN = 16 * 60;

const clockParts = new Intl.DateTimeFormat('en-US', {
  timeZone: JOURNAL_CALENDAR_TIMEZONE, hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit',
});

/** Minutes after midnight ET of an epoch second. */
export function etMinute(epochSec: number): number {
  const parts = clockParts.formatToParts(new Date(epochSec * 1000));
  const part = (type: string) => Number(parts.find(p => p.type === type)?.value ?? 0);
  return part('hour') * 60 + part('minute') + part('second') / 60;
}

/** "14:36" ET of an epoch second. */
export function etClock(epochSec: number): string {
  return hm(etMinute(epochSec));
}

/** "09:30" for a minute of the day. */
export function hm(minute: number): string {
  const m = Math.floor(minute);
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

/** Minutes of an ET "HH:MM". */
export function minutesOf(text: string): number {
  const [h, m] = text.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** One clock for every row shown: 07:00-16:00 at least, widened to whole hours, never past 04:00-20:00. */
export function axisFor(spanLists: readonly (readonly number[][] | undefined)[]): Axis {
  let lo = AXIS_DEFAULT.t0;
  let hi = AXIS_DEFAULT.t1;
  for (const spans of spanLists) {
    for (const [a, b] of spans ?? []) {
      lo = Math.min(lo, etMinute(a));
      hi = Math.max(hi, etMinute(b));
    }
  }
  return { t0: Math.max(AXIS_MIN, Math.floor(lo / 60) * 60), t1: Math.min(AXIS_MAX, Math.ceil(hi / 60) * 60) };
}

/** Where a minute sits on the axis, 0-100. */
export function pct(minute: number, axis: Axis): number {
  const m = Math.max(axis.t0, Math.min(axis.t1, minute));
  return ((m - axis.t0) / (axis.t1 - axis.t0)) * 100;
}

/** Hour labels: every hour, every two on a long clock. */
export function hourTicks(axis: Axis): number[] {
  const step = axis.t1 - axis.t0 > 12 * 60 ? 120 : 60;
  const out: number[] = [];
  for (let m = axis.t0; m <= axis.t1; m += step) out.push(m);
  return out;
}

/** "42s" / "4m 05s" / "1h 12m"; "0s" for none. */
export function durationLabel(sec: number): string {
  const total = Math.max(0, Math.round(sec));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
}

/** "205.3 MB" / "84 KB". */
export function bytesLabel(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
  return `${Math.round(bytes / 1e3)} KB`;
}

export const rowBytes = (row: CaptureSessionRow): number | null =>
  row.bytes ? row.bytes.prints + row.bytes.l2 + row.bytes.quotes : null;

export const recordedSec = (row: CaptureSessionRow): number =>
  (row.spans ?? []).reduce((sum, [a, b]) => sum + Math.max(0, b - a), 0);

export const lastStop = (row: CaptureSessionRow): number | null =>
  (row.spans ?? []).reduce<number | null>((last, [, b]) => (last == null || b > last ? b : last), null);

export const firstStart = (row: CaptureSessionRow): number | null =>
  (row.spans ?? []).reduce<number | null>((first, [a]) => (first == null || a < first ? a : first), null);

/** The gaps the listing names, split: missing data, and stretches stopped on purpose. */
export function gapKinds(row: CaptureSessionRow): { missing: number[][]; planned: number[][] } {
  const missing: number[][] = [];
  const planned: number[][] = [];
  for (const [a, b, reason] of row.gaps ?? []) {
    (reason != null && RECORDS_PLANNED_STOP_REASONS.has(reason) ? planned : missing).push([a, b]);
  }
  return { missing, planned };
}

export type EndedTone = 'live' | 'warn' | 'bad' | 'muted';

/** Who ended a recording, in words (or that it records now). */
export function endedOf(row: CaptureSessionRow, live: boolean): { words: string; tone: EndedTone } {
  if (live) {
    const resumed = row.last_reason ? RECORDS_ENDED_RESUMED[row.last_reason] : undefined;
    return { words: resumed ? `${RECORDS_ENDED_LIVE} · ${resumed}` : RECORDS_ENDED_LIVE, tone: 'live' };
  }
  const unavailable = recordingUnavailableReason(row);
  if (unavailable) return { words: unavailable, tone: 'muted' };
  const byStatus = row.status ? RECORDS_ENDED_STATUS[row.status] : undefined;
  if (byStatus) return byStatus;
  if (row.status === 'stopped_partial_ok' || !row.status) {
    const byReason = row.last_reason ? RECORDS_ENDED_STOPPED[row.last_reason] : undefined;
    if (byReason) return byReason;
  }
  return { words: recordStatusWords(row) ?? '--', tone: 'muted' };
}

/** A count Nova holds, or null (the backend's -1 and unknowns). */
export const counted = (n: number | null | undefined): number | null =>
  n != null && Number.isFinite(n) && n >= 0 ? n : null;

/** Union of spans, merging any that touch within 30 s. */
export function unionSpans(spans: readonly number[][]): number[][] {
  const sorted = [...spans].sort((x, y) => x[0] - y[0]);
  const out: number[][] = [];
  for (const [a, b] of sorted) {
    const last = out[out.length - 1];
    if (last && a <= last[1] + 30) last[1] = Math.max(last[1], b);
    else out.push([a, b]);
  }
  return out;
}

export interface DayRecord {
  date: string;
  row: CaptureSessionRow;
  live: boolean;
  ended: { words: string; tone: EndedTone };
}

export interface DaySummary {
  count: number;
  prints: number;
  l2: number;
  withGaps: number;
  cut: number;
  byYou: number;
  recording: number;
  bytes: number;
  recordedSec: number;
  union: number[][];
}

export function daySummary(records: readonly DayRecord[]): DaySummary {
  const union = unionSpans(records.flatMap(r => r.row.spans ?? []));
  return {
    count: records.length,
    prints: records.reduce((n, r) => n + (counted(r.row.prints) ?? 0), 0),
    l2: records.reduce((n, r) => n + (counted(r.row.l2) ?? 0), 0),
    withGaps: records.filter(r => (r.row.missing_sec ?? 0) > 0).length,
    cut: records.filter(r => isCut(r)).length,
    byYou: records.filter(r => isByYou(r)).length,
    recording: records.filter(r => r.live).length,
    bytes: records.reduce((n, r) => n + (rowBytes(r.row) ?? 0), 0),
    recordedSec: union.reduce((n, [a, b]) => n + (b - a), 0),
    union,
  };
}

export type RecordsFilter = 'all' | 'recording' | 'gaps' | 'cut' | 'you';

const isCut = (r: DayRecord) => !r.live && r.ended.tone === 'warn';
const isByYou = (r: DayRecord) => !r.live && r.row.last_reason === 'operator' && r.row.status === 'stopped_partial_ok';

export function matchesFilter(r: DayRecord, filter: RecordsFilter, query: string): boolean {
  const q = query.trim().toUpperCase();
  if (q && !r.row.symbol.includes(q)) return false;
  if (filter === 'recording') return r.live;
  if (filter === 'gaps') return (r.row.missing_sec ?? 0) > 0;
  if (filter === 'cut') return isCut(r);
  if (filter === 'you') return isByYou(r);
  return true;
}

/** Live first, then the newest stop first: what the table shows before any header is clicked. */
export function newestFirst(a: DayRecord, b: DayRecord): number {
  if (a.live !== b.live) return a.live ? -1 : 1;
  return (lastStop(b.row) ?? 0) - (lastStop(a.row) ?? 0);
}

/** Calendar day in America/New_York as YYYY-MM-DD (the backend's session_date). */
export function todayEasternDate(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: JOURNAL_CALENDAR_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now);
}

/** "Wed, Oct 14" for a YYYY-MM-DD day. */
export function dayLabel(date: string): string {
  const day = new Date(`${date}T12:00:00Z`);
  if (!Number.isFinite(day.getTime())) return date;
  return day.toLocaleDateString('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric' });
}

/** "42s" / "1m 05s" / "5h 12m" for the seconds no segment covers; "--" for none or unknown. */
export function formatMissingSeconds(sec: number | undefined): string {
  if (sec == null || !Number.isFinite(sec) || sec <= 0) return '--';
  return durationLabel(sec);
}

/** "a and b", "a, b and c". */
export function joinWords(words: readonly string[]): string {
  if (words.length <= 1) return words[0] ?? '';
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}
