/**
 * Collapse HOD alerts to one row per ticker (newest-first input).
 * Newest alert supplies price/metrics; distinct strategies become tags.
 *
 * A row is a permanent, timestamp-anchored record: its `id`/`timestamp`/
 * position are pinned to the ticker's first-ever fire today and never move
 * or re-stamp on a later re-fire — only its live snapshot fields and
 * badges/tags update in place. See `collapseAlertsBySymbol` for details.
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
 * @returns One row per ticker. Each row's `id`/`timestamp`/`created_ts` (and
 *   therefore its position) are pinned to that ticker's FIRST-ever fire in
 *   `alerts`, so a row never moves or re-stamps on a later re-fire — only its
 *   live fields (price/metrics from the newest fire) and badges/tags update
 *   in place. Rows are ordered by first-catch time, newest catch on top.
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

  // `alerts` is newest-first, so a ticker's LAST occurrence in the walk is its
  // oldest — i.e. the fire that first caught it today. Anchor each row's
  // identity/position there so re-fires (which only ever add occurrences
  // earlier in this walk) can never move or re-stamp an existing row.
  const firstCatchByTicker = new Map<string, AlertObject>();
  for (let i = alerts.length - 1; i >= 0; i--) {
    const raw = alerts[i];
    if (!firstCatchByTicker.has(raw.ticker)) {
      firstCatchByTicker.set(raw.ticker, raw);
    }
  }

  for (const row of rows) {
    const firstCatch = firstCatchByTicker.get(row.ticker);
    if (!firstCatch) continue;
    row.id = firstCatch.id;
    row.timestamp = firstCatch.timestamp;
    row.created_ts = firstCatch.created_ts;
  }

  rows.sort((a, b) => alertUnix(b) - alertUnix(a));

  return rows;
}
