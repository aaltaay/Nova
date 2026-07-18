/**
 * Collapse HOD alerts to one row per ticker (newest-first input).
 * Newest alert supplies price/metrics; distinct strategies become tags.
 *
 * Warrior-style "(N in Xs)" badges only accumulate fires within a short burst
 * window. Older same-ticker alerts still merge strategy tags but must not
 * inflate the badge into all-day counts like "(1179 in 2157sec)".
 */
import { HOD_MOMO_FORMER_MOMO_STRATEGY_ID } from '../constants';
import type { AlertObject, AlertStrategyTag } from './types';

/** Max gap (seconds) to treat consecutive same-ticker fires as one burst. */
/** Match backend consolidation window (Warrior "(N in Xs)" burst). */
export const HOD_BURST_GAP_SEC = 10;

function alertUnix(a: AlertObject): number {
  if (typeof a.created_ts === 'number' && a.created_ts > 0) return a.created_ts;
  const ms = Date.parse(a.timestamp);
  return Number.isFinite(ms) ? ms / 1000 : 0;
}

function fireCount(a: AlertObject): number {
  return a.consolidation_count > 0 ? a.consolidation_count : 1;
}

function strategyTag(a: AlertObject): AlertStrategyTag {
  return { id: a.strategy_id, name: a.strategy_name };
}

/** Former Momo is disabled — never surface its tag on consolidated rows. */
const HIDDEN_STRATEGY_IDS = new Set([HOD_MOMO_FORMER_MOMO_STRATEGY_ID]);

function visibleStrategyTag(a: AlertObject): AlertStrategyTag | null {
  if (HIDDEN_STRATEGY_IDS.has(a.strategy_id)) return null;
  return strategyTag(a);
}

/**
 * @param alerts Newest-first alert list (already strategy-filtered).
 * @param maxBurstGapSec Burst window for Warrior-style consolidation badge.
 * @returns One row per ticker, same newest-first order of first appearance.
 */
export function collapseAlertsBySymbol(
  alerts: AlertObject[],
  maxBurstGapSec: number = HOD_BURST_GAP_SEC,
): AlertObject[] {
  if (alerts.length === 0) return alerts;

  const gap = Math.max(1, maxBurstGapSec);
  const rows: AlertObject[] = [];
  const indexByTicker = new Map<string, number>();

  for (const raw of alerts) {
    const ticker = raw.ticker;
    const idx = indexByTicker.get(ticker);
    const incomingTag = visibleStrategyTag(raw);
    if (idx == null) {
      indexByTicker.set(ticker, rows.length);
      rows.push({
        ...raw,
        consolidation_count: fireCount(raw),
        consolidated_ids: raw.id
          ? [raw.id, ...(raw.consolidated_ids || [])]
          : [...(raw.consolidated_ids || [])],
        strategies: incomingTag ? [incomingTag] : [],
      });
      continue;
    }

    const row = rows[idx];
    const tags = row.strategies ?? [];
    if (incomingTag && !tags.some(t => t.id === incomingTag.id)) {
      tags.push(incomingTag);
    }
    row.strategies = tags;
    if (raw.id && !row.consolidated_ids.includes(raw.id)) {
      row.consolidated_ids = [
        ...row.consolidated_ids,
        raw.id,
        ...(raw.consolidated_ids || []),
      ];
    }
    const newer = alertUnix(row);
    const older = alertUnix(raw);
    const delta = newer > 0 && older > 0 ? Math.abs(newer - older) : 0;
    // Only extend Warrior burst badge inside the gap; keep strategy tags always.
    if (delta <= gap) {
      row.consolidation_count = (row.consolidation_count || 0) + fireCount(raw);
      const prevSpan = row.consolidation_span_sec ?? 0;
      const nextSpan = raw.consolidation_span_sec ?? 0;
      row.consolidation_span_sec = Math.max(
        1,
        prevSpan,
        nextSpan,
        Math.round(delta) || 1,
      );
    }
  }

  return rows;
}
