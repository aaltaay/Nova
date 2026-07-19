/**
 * Pure ET session classification for chart background shading.
 * Bounds come from constantGroups/market_ui.ts (mirror of backend SESSION_*).
 *
 * Chart bar times are ET wall-clock encoded as UTCTimestamps via isoToEtTime —
 * so getUTCHours/getUTCMinutes on those values yield Eastern clock time.
 */
import type { Time } from 'lightweight-charts';
import {
  CHART_SESSION_COLORS,
  SESSION_AFTERHOURS_END_MIN_ET,
  SESSION_PREMARKET_START_MIN_ET,
  SESSION_RTH_CLOSE_MIN_ET,
  SESSION_RTH_OPEN_MIN_ET,
} from '../constants';

export type MarketSessionKind = 'premarket' | 'rth' | 'afterhours' | 'closed';

/** Intraday timeframes get session bands; daily+ do not. */
export function supportsSessionHighlight(timeframe: string): boolean {
  return /^(?:\d+)(Min|Hour)$/.test(timeframe);
}

export function etMinutesFromChartTime(time: Time): number | null {
  if (typeof time !== 'number' || !Number.isFinite(time)) return null;
  const d = new Date(time * 1000);
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

export function sessionKindFromEtMinutes(minutes: number): MarketSessionKind {
  if (minutes >= SESSION_PREMARKET_START_MIN_ET && minutes < SESSION_RTH_OPEN_MIN_ET) {
    return 'premarket';
  }
  if (minutes >= SESSION_RTH_OPEN_MIN_ET && minutes < SESSION_RTH_CLOSE_MIN_ET) {
    return 'rth';
  }
  if (minutes >= SESSION_RTH_CLOSE_MIN_ET && minutes < SESSION_AFTERHOURS_END_MIN_ET) {
    return 'afterhours';
  }
  return 'closed';
}

export function sessionKindForChartTime(time: Time): MarketSessionKind | null {
  const minutes = etMinutesFromChartTime(time);
  if (minutes == null) return null;
  return sessionKindFromEtMinutes(minutes);
}

export function sessionColorForChartTime(time: Time): string {
  const kind = sessionKindForChartTime(time);
  if (!kind) return 'rgba(0, 0, 0, 0)';
  return CHART_SESSION_COLORS[kind];
}
