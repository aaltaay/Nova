/**
 * Collapse HOD alerts to one row per ticker (newest-first input).
 * Newest alert supplies price/metrics; distinct strategies become tags.
 */
import type { AlertObject, AlertStrategyTag } from './types';

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

/**
 * @param alerts Newest-first alert list (already strategy-filtered).
 * @returns One row per ticker, same newest-first order of first appearance.
 */
export function collapseAlertsBySymbol(alerts: AlertObject[]): AlertObject[] {
  if (alerts.length === 0) return alerts;

  const rows: AlertObject[] = [];
  const indexByTicker = new Map<string, number>();

  for (const raw of alerts) {
    const ticker = raw.ticker;
    const idx = indexByTicker.get(ticker);
    if (idx == null) {
      indexByTicker.set(ticker, rows.length);
      rows.push({
        ...raw,
        consolidation_count: fireCount(raw),
        consolidated_ids: raw.id
          ? [raw.id, ...(raw.consolidated_ids || [])]
          : [...(raw.consolidated_ids || [])],
        strategies: [strategyTag(raw)],
      });
      continue;
    }

    const row = rows[idx];
    const tags = row.strategies ?? [strategyTag(row)];
    if (!tags.some(t => t.id === raw.strategy_id)) {
      tags.push(strategyTag(raw));
    }
    row.strategies = tags;
    row.consolidation_count = (row.consolidation_count || 0) + fireCount(raw);
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
    const prevSpan = row.consolidation_span_sec ?? 0;
    const nextSpan = raw.consolidation_span_sec ?? 0;
    row.consolidation_span_sec = Math.max(
      1,
      prevSpan,
      nextSpan,
      Math.round(delta) || 1,
    );
  }

  return rows;
}
