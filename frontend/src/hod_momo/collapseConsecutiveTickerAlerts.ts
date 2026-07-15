/**
 * Collapse consecutive same-ticker alert rows (newest-first), Warrior-style.
 * Keeps one row per burst and stamps consolidation_count / consolidation_span_sec.
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
