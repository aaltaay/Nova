/**
 * The board's session line: Eastern date, and a countdown to the next
 * regular-session boundary. `Opens in` before 09:30 ET (weekends count down
 * to Monday), `Closes in` during 09:30-16:00, `After hours` otherwise.
 * NYSE holidays are not known to the client -- the title says so.
 */
import { useEffect, useState } from 'react';
import {
  SCANNER_SESSION_AFTER_HOURS,
  SCANNER_SESSION_CLOSES_IN,
  SCANNER_SESSION_OPENS_IN,
  SCANNER_SESSION_TICK_MS,
} from '../constantGroups/scanner_board';
import { SESSION_RTH_CLOSE_MIN_ET, SESSION_RTH_OPEN_MIN_ET } from '../constants';

export type SessionPhase = 'opens' | 'closes' | 'afterhours';

export interface SessionCountdown {
  /** e.g. "Tue Sep 22" (Eastern). */
  dateLabel: string;
  phase: SessionPhase;
  /** "Opens in" / "Closes in" / "After hours". */
  phaseLabel: string;
  /** "48:53" or "1:12:05"; null after hours. */
  countdown: string | null;
}

const ET_WEEKDAY: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

export function etClock(now: Date): { weekday: number; secondsOfDay: number; dateLabel: string } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  const hourRaw = Number(get('hour'));
  const hour = hourRaw === 24 ? 0 : hourRaw;
  const secondsOfDay = hour * 3600 + Number(get('minute')) * 60 + Number(get('second'));
  const weekday = ET_WEEKDAY[get('weekday')] ?? now.getDay();
  return { weekday, secondsOfDay, dateLabel: `${get('weekday')} ${get('month')} ${get('day')}` };
}

export function fmtCountdown(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(sec).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function sessionCountdown(now: Date = new Date()): SessionCountdown {
  const { weekday, secondsOfDay, dateLabel } = etClock(now);
  const open = SESSION_RTH_OPEN_MIN_ET * 60;
  const close = SESSION_RTH_CLOSE_MIN_ET * 60;
  const weekend = weekday === 0 || weekday === 6;

  if (weekend) {
    const daysAhead = weekday === 6 ? 2 : 1;
    return {
      dateLabel,
      phase: 'opens',
      phaseLabel: SCANNER_SESSION_OPENS_IN,
      countdown: fmtCountdown(daysAhead * 86_400 + open - secondsOfDay),
    };
  }
  if (secondsOfDay < open) {
    return { dateLabel, phase: 'opens', phaseLabel: SCANNER_SESSION_OPENS_IN, countdown: fmtCountdown(open - secondsOfDay) };
  }
  if (secondsOfDay < close) {
    return { dateLabel, phase: 'closes', phaseLabel: SCANNER_SESSION_CLOSES_IN, countdown: fmtCountdown(close - secondsOfDay) };
  }
  return { dateLabel, phase: 'afterhours', phaseLabel: SCANNER_SESSION_AFTER_HOURS, countdown: null };
}

const wallClock = (): Date => new Date();

/** 1 Hz session line. `now` must be a stable function (the default is). */
export function useSessionCountdown(now: () => Date = wallClock): SessionCountdown {
  const [value, setValue] = useState(() => sessionCountdown(now()));
  useEffect(() => {
    setValue(sessionCountdown(now()));
    const id = window.setInterval(() => setValue(sessionCountdown(now())), SCANNER_SESSION_TICK_MS);
    return () => window.clearInterval(id);
  }, [now]);
  return value;
}
