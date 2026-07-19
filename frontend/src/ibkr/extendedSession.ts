/**
 * Whether the current Eastern clock is in a tradeable extended session.
 * Used so Flatten / Fill now can set outside_rth on market orders.
 */
import {
  SESSION_AFTERHOURS_END_MIN_ET,
  SESSION_PREMARKET_START_MIN_ET,
  SESSION_RTH_CLOSE_MIN_ET,
  SESSION_RTH_OPEN_MIN_ET,
} from '../constants';
import { sessionKindFromEtMinutes } from '../chart/sessionHighlight';

/** Current minutes since midnight in America/New_York. */
export function etMinutesNow(now: Date = new Date()): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(now);
  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? '0');
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? '0');
  // Intl may emit "24" for midnight in some engines — normalize.
  const h = hour === 24 ? 0 : hour;
  return h * 60 + minute;
}

/** Premarket or after-hours (not RTH, not overnight closed). */
export function isExtendedTradingSessionNow(now: Date = new Date()): boolean {
  const kind = sessionKindFromEtMinutes(etMinutesNow(now));
  return kind === 'premarket' || kind === 'afterhours';
}

/** Prefer EH when the resting order was EH or the clock is in EH. */
export function shouldUseOutsideRth(orderOutsideRth?: boolean | null): boolean {
  return Boolean(orderOutsideRth) || isExtendedTradingSessionNow();
}

/** Re-export session bounds for tests (authoritative in constants). */
export const EXTENDED_SESSION_BOUNDS = {
  premarketStart: SESSION_PREMARKET_START_MIN_ET,
  rthOpen: SESSION_RTH_OPEN_MIN_ET,
  rthClose: SESSION_RTH_CLOSE_MIN_ET,
  afterhoursEnd: SESSION_AFTERHOURS_END_MIN_ET,
} as const;
