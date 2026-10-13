/**
 * The month the day picker draws: a cell per day with a dot on days the feed has, weekends dimmed and future days
 * not pickable. Dates are `YYYY-MM-DD` strings throughout (the feed's own days), so no time zone enters. Pure.
 */

export interface DayCell {
  date: string;
  day: number;
  weekend: boolean;
  future: boolean;
  hasTrades: boolean;
  today: boolean;
  picked: boolean;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
  'November', 'December'];
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const SHORT_MONTHS = MONTHS.map((m) => m.slice(0, 3));

export function iso(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

export function parseIso(date: string): { year: number; month: number; day: number } {
  const [y, m, d] = date.split('-').map(Number);
  return { year: y, month: m - 1, day: d };
}

export function weekday(date: string): number {
  const { year, month, day } = parseIso(date);
  return new Date(Date.UTC(year, month, day)).getUTCDay();
}

/** "Tue, Oct 13". */
export function dayLabel(date: string): string {
  const { month, day } = parseIso(date);
  return `${WEEKDAYS[weekday(date)]}, ${SHORT_MONTHS[month]} ${day}`;
}

export function monthTitle(year: number, month: number): string {
  return `${MONTHS[month]} ${year}`;
}

/** Leading blanks (null) for the weekdays before the 1st, then one cell per day. */
export function monthCells(year: number, month: number, opts: { today: string; withTrades: ReadonlySet<string>;
  picked: string | null }): (DayCell | null)[] {
  const first = new Date(Date.UTC(year, month, 1)).getUTCDay();
  const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const cells: (DayCell | null)[] = Array.from({ length: first }, () => null);
  for (let day = 1; day <= days; day += 1) {
    const date = iso(year, month, day);
    const wd = (first + day - 1) % 7;
    cells.push({
      date,
      day,
      weekend: wd === 0 || wd === 6,
      future: date > opts.today,
      hasTrades: opts.withTrades.has(date),
      today: date === opts.today,
      picked: date === opts.picked,
    });
  }
  return cells;
}

export function shiftMonth(year: number, month: number, by: number): { year: number; month: number } {
  const n = year * 12 + month + by;
  return { year: Math.floor(n / 12), month: ((n % 12) + 12) % 12 };
}

/** The feed's day before or after `date` among `dates` (any order), or null. */
export function neighbourDay(dates: readonly string[], date: string, dir: -1 | 1): string | null {
  const sorted = [...dates].sort();
  if (dir < 0) return sorted.filter((d) => d < date).pop() ?? null;
  return sorted.find((d) => d > date) ?? null;
}
