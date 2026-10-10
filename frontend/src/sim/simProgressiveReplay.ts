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
import { isMassive, type HistoricalJob, type HistoricalSelection } from './historicalTypes';
import { windowKey } from './simReplayOffer';

const ACTIVE = new Set(['running', 'pause_requested']);

/**
 * A window imported from the Massive files (ADR 046) is whole or absent, so it
 * is re-selected once, when an import of it finishes holding something the
 * loaded copy does not: its first import, the bid/ask added once the day's
 * quotes file arrived, or the day's 1-minute bars around it (2026-10-09).
 */
function importChanged(selection: HistoricalSelection, job: HistoricalJob): boolean {
  if (job.status !== 'complete') return false;
  return (job.covered_seconds ?? 0) > (selection.covered_seconds ?? 0)
    || (job.quote_status ?? null) !== (selection.quote_status ?? null)
    || (job.count ?? 0) !== (selection.trade_count ?? 0)
    || (job.quote_count ?? 0) !== (selection.quote_count ?? 0)
    || (job.bar_count ?? 0) !== (selection.bar_count ?? 0);
}

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
  // The selection's own job: an import for a Massive window, a download for an IBKR one.
  const massive = isMassive(selection);
  const job = jobs.find(row => row.kind === 'trades' && windowKey(row) === key && isMassive(row) === massive);
  if (!job) return false;
  if (massive) return importChanged(selection, job);
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
