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

/** Downloaded ranges; a pre-range selection reads as its contiguous prefix. */
export function coverageRanges(selection: HistoricalSelection | null | undefined): number[][] {
  if (!selection) return [];
  if (Array.isArray(selection.coverage)) return selection.coverage;
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
