/**
 * Collapse HOD alerts to one row per ticker (newest-first input).
 * Newest alert supplies price/metrics; distinct strategies become tags.
 *
 * A row is a permanent, timestamp-anchored record: its `id`/`timestamp`/
 * position are pinned to the ticker's first-ever fire today and never move
 * or re-stamp on a later re-fire -- only its live snapshot fields and
 * badges/tags update in place. See `collapseAlertsBySymbol` for details.
 *
 * Warrior-style "(N in Xs)" badges only accumulate fires within a short burst
 * window. Older same-ticker alerts still merge strategy tags but must not
 * inflate the badge into all-day counts like "(1179 in 2157sec)".
 *
 * Ordering / TIME column use trade `timestamp` (not delayed `created_ts`).
 * Backend sets `created_ts` at emit time after consolidation, which can lag
 * the print clock -- sorting on emit time shuffled rows vs the TIME column.
 */
import { HOD_MOMO_FORMER_MOMO_STRATEGY_ID } from '../constants';
import type { AlertObject, AlertStrategyTag } from './types';

/** Max gap (seconds) to treat consecutive same-ticker fires as one burst. */
/** Match backend consolidation window (Warrior "(N in Xs)" burst). */
export const HOD_BURST_GAP_SEC = 10;

/**
 * Clock for TIME column, first-catch pin, burst window, and row order.
 * Prefer trade ISO `timestamp`; fall back to `created_ts` (unix sec or ms).
 */
export function alertDisplayUnix(a: AlertObject): number {
  const ms = Date.parse(a.timestamp);
  if (Number.isFinite(ms) && ms > 0) return ms / 1000;
  const ts = typeof a.created_ts === 'number' ? a.created_ts : 0;
  if (!(ts > 0)) return 0;
  // Backend sends unix seconds; accept ms if already large (same as fmtClock).
  return ts > 1e12 ? ts / 1000 : ts;
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
 *   `alerts` by trade TIME, so a row never moves or re-stamps on a later
 *   re-fire -- only its live fields (price/metrics from the newest fire) and
 *   badges/tags update in place. Rows are ordered by first-catch TIME,
 *   newest catch on top (matches the TIME column).
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
    const newer = alertDisplayUnix(row);
    const older = alertDisplayUnix(raw);
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

  // First catch = earliest trade TIME for that ticker (not earliest emit /
  // created_ts -- consolidation can delay created_ts by many seconds).
  const firstCatchByTicker = new Map<string, AlertObject>();
  for (const raw of alerts) {
    const prev = firstCatchByTicker.get(raw.ticker);
    if (!prev || alertDisplayUnix(raw) < alertDisplayUnix(prev)) {
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

  rows.sort((a, b) => alertDisplayUnix(b) - alertDisplayUnix(a));

  return rows;
}
