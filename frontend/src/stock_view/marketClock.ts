/**
 * Pure Eastern market clock helpers for Stock View header.
 */
import { sessionKindFromEtMinutes, type MarketSessionKind } from '../chart/sessionHighlight';
import {
  STOCK_VIEW_CLOCK_SESSION_LABELS,
  STOCK_VIEW_CLOCK_TIMEZONE,
} from '../constants';
import { etMinutesNow } from '../ibkr/extendedSession';

export type MarketClockSnapshot = {
  timeLabel: string;
  sessionKind: MarketSessionKind;
  sessionLabel: string;
};

/** Format `now` as HH:MM:SS ET + session kind (premarket / RTH / …). */
export function marketClockSnapshot(now: Date = new Date()): MarketClockSnapshot {
  const timeLabel = new Intl.DateTimeFormat('en-US', {
    timeZone: STOCK_VIEW_CLOCK_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(now);
  const sessionKind = sessionKindFromEtMinutes(etMinutesNow(now));
  return {
    timeLabel: `${timeLabel} ET`,
    sessionKind,
    sessionLabel: STOCK_VIEW_CLOCK_SESSION_LABELS[sessionKind],
  };
}
