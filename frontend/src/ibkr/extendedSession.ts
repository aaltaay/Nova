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
import {
  sessionKindFromEtMinutes,
  type MarketSessionKind,
} from '../chart/sessionHighlight';

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

/** Current ET session kind (premarket / rth / afterhours / closed). */
export function sessionKindNow(now: Date = new Date()) {
  return sessionKindFromEtMinutes(etMinutesNow(now));
}

/** Premarket or after-hours (not RTH, not overnight closed). */
export function isExtendedTradingSessionNow(now: Date = new Date()): boolean {
  const kind = sessionKindNow(now);
  return kind === 'premarket' || kind === 'afterhours';
}

/** Prefer EH when the resting order was EH or the clock is in EH. */
export function shouldUseOutsideRth(orderOutsideRth?: boolean | null): boolean {
  return Boolean(orderOutsideRth) || isExtendedTradingSessionNow();
}

const ET_WEEKDAY_INDEX: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
};

/** 0 = Sunday ... 6 = Saturday in America/New_York. */
export function etWeekdayNow(now: Date = new Date()): number {
  const wd = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
  }).format(now);
  return ET_WEEKDAY_INDEX[wd] ?? now.getDay();
}

/** Weekday RTH only -- Saturday 10:30 ET is not regular hours. */
export function isWeekdayRegularHoursNow(now: Date = new Date()): boolean {
  const day = etWeekdayNow(now);
  if (day === 0 || day === 6) return false;
  return sessionKindNow(now) === 'rth';
}

export function flattenNeedsOutsideRth(
  now?: Date,
  sessionKind?: MarketSessionKind,
): boolean {
  if (sessionKind) return sessionKind !== 'rth';
  return !isWeekdayRegularHoursNow(now ?? new Date());
}

export function resolveFillSessionKind(options?: {
  sessionKind?: MarketSessionKind;
  now?: Date;
}): MarketSessionKind {
  if (options?.sessionKind) return options.sessionKind;
  const now = options?.now ?? new Date();
  const day = etWeekdayNow(now);
  if (day === 0 || day === 6) return 'closed';
  return sessionKindFromEtMinutes(etMinutesNow(now));
}

/** Re-export session bounds for tests (authoritative in constants). */
export const EXTENDED_SESSION_BOUNDS = {
  premarketStart: SESSION_PREMARKET_START_MIN_ET,
  rthOpen: SESSION_RTH_OPEN_MIN_ET,
  rthClose: SESSION_RTH_CLOSE_MIN_ET,
  afterhoursEnd: SESSION_AFTERHOURS_END_MIN_ET,
} as const;
