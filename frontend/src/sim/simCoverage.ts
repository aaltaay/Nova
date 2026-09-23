/**
 * Where downloaded trades end, relative to the replay window and the playhead.
 *
 * A download fills its window forward, and the operator can scrub anywhere in
 * it. Past the download edge there are no prints for that moment yet -- but the
 * snapshot still returns the last prints before the playhead, which are the
 * edge's, so a tape at 11:00 would silently show 09:40. These helpers let the
 * slider show the edge (like a video player's buffered band) and the tape say
 * "not downloaded yet" instead of passing old prints off as current.
 */
import type { HistoricalSelection } from './historicalTypes';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';
import type { CaptureSegment, SimClockState } from './simClockTypes';
import { RECORDING_PLANNED_STOP_REASONS } from '../capture/constants';

/** A `[start, end)` pair of finite epoch seconds with end after start. */
const isRange = (pair: unknown): pair is [number, number] => Array.isArray(pair) && pair.length === 2
  && Number.isFinite(pair[0]) && Number.isFinite(pair[1]) && pair[1] > pair[0];

/**
 * Downloaded ranges; a pre-range selection reads as its contiguous prefix. Only
 * well-formed pairs count -- one `null` element used to take the desk down (C6).
 */
export function coverageRanges(selection: HistoricalSelection | null | undefined): number[][] {
  if (!selection) return [];
  if (Array.isArray(selection.coverage)) return selection.coverage.filter(isRange);
  const { start_ts: start, coverage_through: through } = selection;
  return start != null && through != null && through > start ? [[start, through]] : [];
}

/** Downloaded share of the window, 0..1; null when unknown. */
export function coverageFraction(selection: HistoricalSelection | null | undefined): number | null {
  if (!selection) return null;
  const { start_ts: start, end_ts: end } = selection;
  if (start == null || end == null || end <= start) return null;
  const covered = coverageRanges(selection).reduce((sum, [a, b]) => sum + (b - a), 0);
  return Math.max(0, Math.min(1, covered / (end - start)));
}

/** Each downloaded range as slider-relative left/width fractions, for the band. */
export function coverageSegments(
  selection: HistoricalSelection | null | undefined,
): { left: number; width: number }[] {
  const start = selection?.start_ts;
  const end = selection?.end_ts;
  if (start == null || end == null || end <= start) return [];
  return coverageRanges(selection).map(([a, b]) => ({
    left: (Math.max(a, start) - start) / (end - start),
    width: (Math.min(b, end) - Math.max(a, start)) / (end - start),
  })).filter(segment => segment.width > 0);
}

/** The playhead's second is not downloaded (past the edge, or in a gap). */
export function playheadBeyondCoverage(snapshot: HistoricalSnapshot | null | undefined): boolean {
  if (!snapshot || snapshot.source === 'completed_bars') return false;
  // The backend decides against its own ranges; trust it when it says.
  if (typeof snapshot.covered === 'boolean') return !snapshot.covered;
  const through = snapshot.selection?.coverage_through;
  if (through == null) return false;
  const playhead = Date.parse(snapshot.as_of) / 1000;
  return Number.isFinite(playhead) && playhead > through;
}

/** "09:15-09:38, 11:05-11:12" -- the downloaded ranges, for a tooltip. */
export function coverageLabel(
  selection: HistoricalSelection | null | undefined,
  format: (epochSeconds: number) => string,
): string {
  return coverageRanges(selection).map(([a, b]) => `${format(a)}–${format(b)}`).join(', ');
}

/** A slider-relative stretch of a loaded capture: recorded, or a gap between recordings. */
export interface CaptureBandSegment {
  left: number;
  width: number;
  kind: 'recorded' | 'gap';
  /** For a gap: why the recording before it ended. */
  reason: string | null;
}

function epoch(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

interface Span { start: number; stop: number; reason: string | null }

/**
 * A segment somebody stopped on purpose -- the operator, or auto-record's own
 * planned stop (ADR 022): the gap after it is not "missing".
 */
const isPlannedStop = (reason: string | null): boolean => reason != null && RECORDING_PLANNED_STOP_REASONS.has(reason);

/**
 * Recorded spans, merged where they overlap, in time order. An open segment
 * (`stopped_et: null`, the one still recording) runs to now, never past the
 * session end -- the future is not recorded (C41). Anything but a list of
 * segment objects reads as no segments (C6).
 */
export function captureSpans(
  segments: CaptureSegment[] | null | undefined,
  sessionEnd: number,
  now: number = Date.now() / 1000,
): Span[] {
  const spans: Span[] = [];
  for (const segment of Array.isArray(segments) ? segments : []) {
    if (!segment || typeof segment !== 'object') continue;
    const start = epoch(segment.started_et);
    if (start == null) continue;
    const stop = Math.max(start, epoch(segment.stopped_et) ?? Math.min(sessionEnd, now));
    spans.push({ start, stop, reason: segment.reason ?? null });
  }
  spans.sort((a, b) => a.start - b.start);
  const merged: Span[] = [];
  for (const span of spans) {
    const last = merged[merged.length - 1];
    if (last && span.start <= last.stop) {
      last.stop = Math.max(last.stop, span.stop);
      last.reason = span.reason;
    } else {
      merged.push({ ...span });
    }
  }
  return merged;
}

/**
 * Where a loaded capture recorded, against the session the scrubber spans, and
 * the gaps between recordings. A quiet stretch inside one recording is not a
 * gap: the recorder was up and the tape said nothing.
 */
export function captureBandSegments(clock: SimClockState | null | undefined): CaptureBandSegment[] {
  const open = epoch(clock?.session_open_et);
  const close = epoch(clock?.session_close_et);
  if (open == null || close == null || close <= open) return [];
  const spans = captureSpans(clock?.replay_load?.segments, close);
  const fraction = (a: number, b: number) => ({
    left: (Math.max(a, open) - open) / (close - open),
    width: (Math.min(b, close) - Math.max(a, open)) / (close - open),
  });
  const out: CaptureBandSegment[] = [];
  spans.forEach((span, index) => {
    out.push({ ...fraction(span.start, span.stop), kind: 'recorded', reason: null });
    const next = spans[index + 1];
    if (next && next.start > span.stop) {
      out.push({ ...fraction(span.stop, next.start), kind: 'gap', reason: span.reason });
    }
  });
  return out.filter(segment => segment.width > 0);
}

/**
 * Seconds no recording covers between the first start and the last stop,
 * except the gaps the operator made by stopping on purpose (C64) -- those
 * were not recorded, but nothing went missing.
 */
export function captureMissingSeconds(clock: SimClockState | null | undefined): number {
  const close = epoch(clock?.session_close_et) ?? Number.MAX_SAFE_INTEGER;
  const spans = captureSpans(clock?.replay_load?.segments, close);
  let missing = 0;
  for (let i = 1; i < spans.length; i += 1) {
    if (isPlannedStop(spans[i - 1].reason)) continue;
    missing += Math.max(0, spans[i].start - spans[i - 1].stop);
  }
  return Math.round(missing);
}

/** "4m 12s" / "35s" / "1h 02m" for a gap. */
export function missingLabel(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}

/** "Recorded 11:46-11:47, 12:03-12:40 · 16m 12s missing (failure)" for the band tooltip. */
export function captureCoverageLabel(
  clock: SimClockState | null | undefined,
  format: (epochSeconds: number) => string,
): string {
  const close = epoch(clock?.session_close_et) ?? Number.MAX_SAFE_INTEGER;
  const spans = captureSpans(clock?.replay_load?.segments, close);
  if (!spans.length) return '';
  const ranges = spans.map(span => `${format(span.start)}–${format(span.stop)}`).join(', ');
  const missing = captureMissingSeconds(clock);
  const reasons = Array.from(new Set(spans.slice(0, -1).map(span => span.reason)
    .filter(reason => reason && !isPlannedStop(reason)))).join(', ');
  return missing > 0
    ? `Recorded ${ranges} · ${missingLabel(missing)} missing${reasons ? ` (${reasons})` : ''}`
    : `Recorded ${ranges}`;
}
