/**
 * Collapse consecutive same-ticker alert rows (newest-first), Warrior-style.
 * Keeps one row per burst and stamps consolidation_count / consolidation_span_sec.
 *
 * Also exports `incrementalCollapse` for O(new-head) re-collapse when only
 * new alerts are prepended to an already-collapsed list.
 */
import type { AlertObject } from './types';

function alertUnix(a: AlertObject): number {
  if (typeof a.created_ts === 'number' && a.created_ts > 0) return a.created_ts;
  const ms = Date.parse(a.timestamp);
  return Number.isFinite(ms) ? ms / 1000 : 0;
}

/**
 * @param maxGapSec Merge consecutive same-ticker rows when their timestamps
 *   are within this many seconds (covers already-emitted unconsolidated spam).
 */
export function collapseConsecutiveTickerAlerts(
  alerts: AlertObject[],
  maxGapSec: number,
): AlertObject[] {
  if (alerts.length === 0) return alerts;
  const gap = Math.max(1, maxGapSec);
  const out: AlertObject[] = [];

  for (const raw of alerts) {
    const a = { ...raw };
    const prev = out.length > 0 ? out[out.length - 1] : null;
    if (!prev || prev.ticker !== a.ticker) {
      out.push(a);
      continue;
    }
    const newer = alertUnix(prev);
    const older = alertUnix(a);
    const delta = newer > 0 && older > 0 ? Math.abs(newer - older) : 0;
    if (delta > gap) {
      out.push(a);
      continue;
    }
    const prevCount = prev.consolidation_count > 0 ? prev.consolidation_count : 1;
    const nextCount = a.consolidation_count > 0 ? a.consolidation_count : 1;
    prev.consolidation_count = prevCount + nextCount;
    const prevSpan = prev.consolidation_span_sec ?? 0;
    const nextSpan = a.consolidation_span_sec ?? 0;
    prev.consolidation_span_sec = Math.max(1, prevSpan, nextSpan, Math.round(delta) || 1);
    if (a.id && !prev.consolidated_ids.includes(a.id)) {
      prev.consolidated_ids = [...prev.consolidated_ids, a.id, ...(a.consolidated_ids || [])];
    }
    // Keep newer row's price / strategy (prev is newer in newest-first list).
  }
  return out;
}

/**
 * Incremental re-collapse for prepend-only lists.
 * Only collapses `newHead` (the freshly prepended alerts) and checks whether
 * the last item of the collapsed head can be merged into the first item of
 * `prevCollapsed`. The rest of `prevCollapsed` is returned by reference, so
 * `memo` on `HodMomoAlertRow` short-circuits for unchanged rows.
 *
 * @param newHead   Newly prepended alerts in newest-first order (not yet in prevCollapsed).
 * @param prevCollapsed  Previously collapsed list; may be empty on first call.
 * @param maxGapSec  Same window used for the original collapse.
 */
export function incrementalCollapse(
  newHead: AlertObject[],
  prevCollapsed: AlertObject[],
  maxGapSec: number,
): AlertObject[] {
  if (newHead.length === 0) return prevCollapsed;
  const gap = Math.max(1, maxGapSec);
  const headCollapsed = collapseConsecutiveTickerAlerts(newHead, gap);
  if (prevCollapsed.length === 0) return headCollapsed;

  const last = headCollapsed[headCollapsed.length - 1];
  const first = prevCollapsed[0];

  if (last.ticker !== first.ticker) {
    return [...headCollapsed, ...prevCollapsed];
  }

  // Timestamps in newest-first order: last (from new head) is newer than first (from prev).
  const newerTs = alertUnix(last);
  const olderTs = alertUnix(first);
  const delta = newerTs > 0 && olderTs > 0 ? newerTs - olderTs : Infinity;

  if (delta > gap) {
    return [...headCollapsed, ...prevCollapsed];
  }

  // Merge boundary items — keep newer item's price/strategy (last).
  const merged: AlertObject = { ...last };
  const prevCount = first.consolidation_count > 0 ? first.consolidation_count : 1;
  const newCount = last.consolidation_count > 0 ? last.consolidation_count : 1;
  merged.consolidation_count = newCount + prevCount;
  const prevSpan = first.consolidation_span_sec ?? 0;
  const newSpan = last.consolidation_span_sec ?? 0;
  merged.consolidation_span_sec = Math.max(1, prevSpan, newSpan, Math.round(delta) || 1);
  if (first.id && !merged.consolidated_ids.includes(first.id)) {
    merged.consolidated_ids = [...merged.consolidated_ids, first.id, ...first.consolidated_ids];
  }

  // prevCollapsed.slice(1) reuses existing object references → memo short-circuits.
  return [...headCollapsed.slice(0, -1), merged, ...prevCollapsed.slice(1)];
}
