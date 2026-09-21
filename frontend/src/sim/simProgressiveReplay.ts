/**
 * Progressive historical replay: practise from the first page, not the last.
 *
 * A download fills its window forward from the first second at IBKR's pace
 * (1000 prints per request, ~11 s apart), and a replay plays the same window
 * forward from the same second at 1x. So the operator never has to wait for the
 * whole download -- only for coverage to stay ahead of the playhead, which it
 * does for most tapes. Re-selecting the same window keeps the playhead
 * (`history_playback.select`), and past coverage the snapshot already falls
 * back to candles, so folding new prints in is invisible except as more tape.
 */
import type { HistoricalJob, HistoricalSelection } from './historicalTypes';
import { windowKey } from './simReplayOffer';

const ACTIVE = new Set(['running', 'pause_requested']);

/**
 * The loaded selection needs a quiet re-select: its own trades job has
 * committed prints past what was loaded -- still running, or finished since.
 * Throttled while running, so a busy tape does not re-materialise every poll.
 */
export function shouldRefreshSelection(
  selection: HistoricalSelection | null | undefined,
  jobs: readonly HistoricalJob[],
  lastRefreshAt: number,
  now: number,
  intervalMs: number,
): boolean {
  if (!selection) return false;
  const key = windowKey(selection);
  const job = jobs.find(row => row.kind === 'trades' && windowKey(row) === key);
  if (!job) return false;
  // Coverage can grow anywhere (jump ahead, backfill), so compare covered time,
  // not cursors; pre-range payloads fall back to the contiguous cursor.
  const gained = job.covered_seconds != null && selection.covered_seconds != null
    ? job.covered_seconds > selection.covered_seconds
    : job.cursor != null && job.cursor > (selection.coverage_through ?? 0);
  if (!gained) return false;
  // Finished since the last load: fold the tail in now, not a throttle later.
  if (job.status === 'complete') return true;
  if (!ACTIVE.has(job.status) || job.stale) return false;
  return now - lastRefreshAt >= intervalMs;
}
