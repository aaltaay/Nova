/**
 * The phone calendar's two derivations over the desk's own history: the month laid out for a narrow
 * screen, and one past day's P&L line. Pure. The figures are the desk's (`account/accountCalendar`,
 * `account/accountDayBreakdown`); only the layout is the phone's.
 */
import type { CalendarCell, CalendarMonth } from '../account/accountCalendar';
import { fillDay } from '../account/accountDayBreakdown';
import type { SeriesPoint } from '../account/equityPath';
import type { PracticeHistory } from '../account/accountHistoryTypes';

export interface PhoneMonth {
  /** 5 (Monday to Friday) unless a Saturday or Sunday traded this month, then 7. */
  columns: 5 | 7;
  /** Week rows, each `columns` cells; a week with no day of this month in view is left out. */
  cells: CalendarCell[];
}

/** The month as the phone shows it: weekdays only, so a square is wide enough for its figure. */
export function phoneMonth(grid: CalendarMonth): PhoneMonth {
  const weekendTraded = grid.cells.some((c) => c.weekend && c.pnl != null);
  const columns = weekendTraded ? 7 : 5;
  const cells: CalendarCell[] = [];
  for (let i = 0; i < grid.cells.length; i += 7) {
    const week = grid.cells.slice(i, i + 7);
    const shown = weekendTraded ? week : week.slice(1, 6);
    if (shown.some((c) => c.day != null)) cells.push(...shown);
  }
  return { columns, cells };
}

/**
 * One practice day's P&L from zero, at each of that day's fills: the history's own event points
 * (realized + open at the event's marks) less where the account stood before the day. Empty when the
 * history holds no point for the day (an archived ledger sends only totals).
 */
export function daySeries(history: PracticeHistory, date: string): SeriesPoint[] {
  const at = (i: number): number => history.equity[i].realized + history.equity[i].unrealized;
  const first = history.equity.findIndex((p) => fillDay(p.ts) === date);
  if (first < 0) return [];
  const before = first > 0 ? at(first - 1) : 0;
  const series: SeriesPoint[] = [{ ts: history.equity[first].ts, value: 0 }];
  for (let i = first; i < history.equity.length && fillDay(history.equity[i].ts) === date; i++) {
    series.push({ ts: history.equity[i].ts, value: at(i) - before });
  }
  return series;
}
