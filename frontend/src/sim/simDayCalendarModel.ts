/**
 * Pure model for the Sim Day calendar (ADR 023): which days have what, and the
 * month grid. A day can carry three independent facts, each from its own source:
 *
 * - rebuilt:  a Scanner board rebuilt from the minute flat files;
 * - recorded: a Scanner board Nova's own recorder saved while the desk ran;
 * - sessions: the operator's own Session Records (tape + Level 2) of symbols.
 *
 * Nothing is inferred: a day with none of the three is not selectable, and a
 * Session Record on a non-exchange day is shown but cannot be opened (the Sim
 * clock refuses a closed day).
 */
import type { LeaderboardDay } from '../leaderboard/leaderboardTypes';
import type { CaptureSessions } from './useSimSessionController';

export interface CalendarDayFacts {
  rebuilt: boolean;
  recorded: boolean;
  /** Usable Session Records on this day, by symbol. */
  sessions: string[];
}

export interface CalendarCell {
  date: string;
  day: number;
  inMonth: boolean;
  weekend: boolean;
  facts: CalendarDayFacts;
  selectable: boolean;
  today: boolean;
  selected: boolean;
}

const NONE: CalendarDayFacts = { rebuilt: false, recorded: false, sessions: [] };

export function dayFacts(days: LeaderboardDay[], sessions: CaptureSessions | null | undefined): Map<string, CalendarDayFacts> {
  const out = new Map<string, CalendarDayFacts>();
  const entry = (date: string) => {
    let facts = out.get(date);
    if (!facts) {
      facts = { rebuilt: false, recorded: false, sessions: [] };
      out.set(date, facts);
    }
    return facts;
  };
  for (const day of days) {
    const facts = entry(day.date);
    facts.rebuilt = facts.rebuilt || day.reconstructed != null;
    facts.recorded = facts.recorded || day.recorded != null;
  }
  for (const [date, rows] of Object.entries(sessions?.tickers_by_day ?? {})) {
    const usable = rows.filter(row => row.usable !== false && row.empty !== true).map(row => row.symbol);
    if (usable.length) entry(date).sessions = [...new Set(usable)].sort();
  }
  return out;
}

const pad = (n: number) => String(n).padStart(2, '0');
export const isoDay = (year: number, month0: number, day: number) => `${year}-${pad(month0 + 1)}-${pad(day)}`;

/** Weekday of an ISO date, 0 = Sunday, computed in UTC so no local zone shifts it. */
export function weekdayOf(date: string): number {
  return new Date(`${date}T12:00:00Z`).getUTCDay();
}

export interface MonthRef { year: number; month0: number }

export function monthOf(date: string): MonthRef {
  return { year: Number(date.slice(0, 4)), month0: Number(date.slice(5, 7)) - 1 };
}

export function shiftMonth(ref: MonthRef, delta: number): MonthRef {
  const index = ref.year * 12 + ref.month0 + delta;
  return { year: Math.floor(index / 12), month0: ((index % 12) + 12) % 12 };
}

/** Weeks of a month, Sunday first, padded with the neighbouring months' days. */
export function monthGrid(
  ref: MonthRef,
  facts: Map<string, CalendarDayFacts>,
  today: string,
  selected: string | null,
): CalendarCell[][] {
  const first = new Date(Date.UTC(ref.year, ref.month0, 1));
  const start = new Date(first);
  start.setUTCDate(1 - first.getUTCDay());
  const weeks: CalendarCell[][] = [];
  const cursor = new Date(start);
  do {
    const week: CalendarCell[] = [];
    for (let i = 0; i < 7; i += 1) {
      const date = isoDay(cursor.getUTCFullYear(), cursor.getUTCMonth(), cursor.getUTCDate());
      const f = facts.get(date) ?? NONE;
      const weekend = i === 0 || i === 6;
      const hasAny = f.rebuilt || f.recorded || f.sessions.length > 0;
      week.push({
        date,
        day: cursor.getUTCDate(),
        inMonth: cursor.getUTCMonth() === ref.month0,
        weekend,
        facts: f,
        selectable: hasAny && !weekend && date <= today,
        today: date === today,
        selected: date === selected,
      });
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    weeks.push(week);
  } while (cursor.getUTCMonth() === ref.month0);
  return weeks;
}

/** The months the calendar can reach: from the oldest day on file to today's month. */
export function monthRange(facts: Map<string, CalendarDayFacts>, today: string): { first: MonthRef; last: MonthRef } {
  const dates = [...facts.keys()].sort();
  return { first: monthOf(dates[0] ?? today), last: monthOf(today) };
}

export const monthIndex = (ref: MonthRef) => ref.year * 12 + ref.month0;

/** One line per fact, for the day's tooltip. */
export function cellTitle(cell: CalendarCell, labels: {
  rebuilt: string; recorded: string; sessions: (symbols: string[]) => string; nothing: string; closed: string;
}): string {
  const lines: string[] = [cell.date];
  if (cell.facts.recorded) lines.push(labels.recorded);
  if (cell.facts.sessions.length) lines.push(labels.sessions(cell.facts.sessions));
  if (cell.facts.rebuilt) lines.push(labels.rebuilt);
  if (lines.length === 1) lines.push(labels.nothing);
  else if (cell.weekend) lines.push(labels.closed);
  return lines.join('\n');
}
