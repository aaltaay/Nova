/**
 * Month grid for the Calendar panel from the history's `daily` rows. Pure.
 * A date can carry two rows (a reset mid-day): the cell sums them and is
 * "archived" only when every row is. Weekends are "no session"; a weekday
 * without a row is blank -- there is no holiday calendar on the client, so
 * nothing labels one.
 */
import type { HistoryDaily } from './accountHistoryTypes';

export interface CalendarCell {
  /** Day of month, or null for a leading / trailing blank. */
  day: number | null;
  date: string | null;
  weekend: boolean;
  today: boolean;
  /** Net P&L of the day (realized - commissions - fees), or null with no row. */
  pnl: number | null;
  fills: number;
  archived: boolean;
}

export interface CalendarMonth {
  year: number;
  /** 0-based month. */
  month: number;
  cells: CalendarCell[];
  archivedTotal: number;
  currentTotal: number;
  /** Rows in this month. */
  rows: number;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export const monthLabel = (year: number, month: number): string => `${MONTH_NAMES[month]} ${year}`;

export function parseIsoDate(date: string): { year: number; month: number; day: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!m) return null;
  return { year: Number(m[1]), month: Number(m[2]) - 1, day: Number(m[3]) };
}

export const isoDate = (year: number, month: number, day: number): string =>
  `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
  const index = year * 12 + month + delta;
  return { year: Math.floor(index / 12), month: ((index % 12) + 12) % 12 };
}

export const dayNet = (row: HistoryDaily): number => row.realized - row.commissions - row.fees;

export function monthGrid(year: number, month: number, daily: HistoryDaily[], today: string): CalendarMonth {
  const prefix = isoDate(year, month, 1).slice(0, 7);
  const byDate = new Map<string, HistoryDaily[]>();
  for (const row of daily) {
    if (!row.date.startsWith(prefix)) continue;
    const list = byDate.get(row.date) ?? [];
    list.push(row);
    byDate.set(row.date, list);
  }
  const firstWeekday = new Date(Date.UTC(year, month, 1)).getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const cells: CalendarCell[] = [];
  const blank = (): CalendarCell => ({
    day: null, date: null, weekend: false, today: false, pnl: null, fills: 0, archived: false,
  });
  for (let i = 0; i < firstWeekday; i++) cells.push(blank());
  let archivedTotal = 0;
  let currentTotal = 0;
  let rows = 0;
  for (let day = 1; day <= daysInMonth; day++) {
    const date = isoDate(year, month, day);
    const weekday = (firstWeekday + day - 1) % 7;
    const list = byDate.get(date) ?? [];
    let pnl: number | null = null;
    let fills = 0;
    for (const row of list) {
      const net = dayNet(row);
      pnl = (pnl ?? 0) + net;
      fills += row.fills;
      if (row.archived) archivedTotal += net;
      else currentTotal += net;
      rows++;
    }
    cells.push({
      day,
      date,
      weekend: weekday === 0 || weekday === 6,
      today: date === today,
      pnl,
      fills,
      archived: list.length > 0 && list.every((row) => row.archived),
    });
  }
  while (cells.length % 7 !== 0) cells.push(blank());
  return { year, month, cells, archivedTotal, currentTotal, rows };
}
