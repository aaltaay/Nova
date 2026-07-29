/**
 * Per-row height + strategy-tag helpers for the HOD alert table.
 * Multi-strategy rows stack pills vertically, so row height grows with tag count
 * and the virtualizer uses prefix offsets instead of a single fixed height.
 */
import {
  HOD_MOMO_FORMER_MOMO_STRATEGY_ID,
  HOD_MOMO_MAX_INLINE_STRATEGY_PILLS,
  HOD_MOMO_ROW_HEIGHT_PX,
  HOD_MOMO_STRATEGY_PILL_LINE_PX,
} from '../constants';
import type { AlertObject, AlertStrategyTag } from './types';

export function visibleStrategyTags(alert: AlertObject): AlertStrategyTag[] {
  const tags = (
    alert.strategies?.length
      ? alert.strategies
      : [{ id: alert.strategy_id, name: alert.strategy_name }]
  ).filter(tag => tag.id !== HOD_MOMO_FORMER_MOMO_STRATEGY_ID);
  return tags;
}

/** Row height for one alert (base + extra lines for stacked strategy pills). */
export function hodMomoAlertRowHeightPx(alert: AlertObject): number {
  const n = visibleStrategyTags(alert).length;
  const stacked = Math.max(1, Math.min(n, HOD_MOMO_MAX_INLINE_STRATEGY_PILLS));
  return HOD_MOMO_ROW_HEIGHT_PX + (stacked - 1) * HOD_MOMO_STRATEGY_PILL_LINE_PX;
}

/** Prefix sums: offsets[i] = pixel offset of row i; offsets[n] = total height. */
export function buildHodMomoRowOffsets(alerts: AlertObject[]): number[] {
  const offsets = new Array<number>(alerts.length + 1);
  offsets[0] = 0;
  for (let i = 0; i < alerts.length; i++) {
    offsets[i + 1] = offsets[i] + hodMomoAlertRowHeightPx(alerts[i]);
  }
  return offsets;
}

/** Largest row index i with offsets[i] <= y (clamped). */
export function findRowAtOffset(offsets: number[], y: number): number {
  const last = offsets.length - 2;
  if (last < 0) return 0;
  let lo = 0;
  let hi = last;
  const target = Math.max(0, y);
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (offsets[mid] <= target) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}
