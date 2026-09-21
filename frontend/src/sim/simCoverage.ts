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

/** Downloaded share of the window, 0..1; null when unknown. */
export function coverageFraction(selection: HistoricalSelection | null | undefined): number | null {
  if (!selection) return null;
  const { start_ts: start, end_ts: end, coverage_through: through } = selection;
  if (start == null || end == null || through == null || end <= start) return null;
  return Math.max(0, Math.min(1, (through - start) / (end - start)));
}

/** The playhead is past the last downloaded print of a trades replay. */
export function playheadBeyondCoverage(snapshot: HistoricalSnapshot | null | undefined): boolean {
  const through = snapshot?.selection?.coverage_through;
  if (!snapshot || through == null || snapshot.source === 'completed_bars') return false;
  const playhead = Date.parse(snapshot.as_of) / 1000;
  return Number.isFinite(playhead) && playhead > through;
}
