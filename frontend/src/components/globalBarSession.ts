/**
 * Session chip on the global bar: PREMARKET / OPEN / AFTER HOURS / CLOSED
 * from the client's Eastern clock. Weekends are closed; NYSE holidays are not
 * known here, and the title says so. Pure -- the component only ticks it.
 */
import {
  GLOBAL_BAR_SESSION_HOLIDAY_NOTE,
  GLOBAL_BAR_SESSION_LABELS,
  GLOBAL_BAR_SESSION_WORDS,
  SESSION_AFTERHOURS_END_MIN_ET,
  SESSION_PREMARKET_START_MIN_ET,
  SESSION_RTH_CLOSE_MIN_ET,
  SESSION_RTH_OPEN_MIN_ET,
} from '../constants';
import { resolveFillSessionKind } from '../ibkr/extendedSession';

export type SessionChipKind = keyof typeof GLOBAL_BAR_SESSION_LABELS;

export interface SessionChipView {
  kind: SessionChipKind;
  label: string;
  title: string;
}

function hhmm(minutesOfDay: number): string {
  const h = Math.floor(minutesOfDay / 60);
  const m = minutesOfDay % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

const SESSION_RANGE: Record<SessionChipKind, [number, number] | null> = {
  premarket: [SESSION_PREMARKET_START_MIN_ET, SESSION_RTH_OPEN_MIN_ET],
  open: [SESSION_RTH_OPEN_MIN_ET, SESSION_RTH_CLOSE_MIN_ET],
  afterhours: [SESSION_RTH_CLOSE_MIN_ET, SESSION_AFTERHOURS_END_MIN_ET],
  closed: null,
};

export function sessionChipKind(now: Date): SessionChipKind {
  const kind = resolveFillSessionKind({ now });
  return kind === 'rth' ? 'open' : kind;
}

export function sessionChipTitle(kind: SessionChipKind): string {
  const range = SESSION_RANGE[kind];
  const words = GLOBAL_BAR_SESSION_WORDS[kind];
  const span = range ? ` ${hhmm(range[0])}-${hhmm(range[1])} ET.` : '.';
  return `${words}${span} ${GLOBAL_BAR_SESSION_HOLIDAY_NOTE}`;
}

export function sessionChipView(now: Date = new Date()): SessionChipView {
  const kind = sessionChipKind(now);
  return { kind, label: GLOBAL_BAR_SESSION_LABELS[kind], title: sessionChipTitle(kind) };
}
