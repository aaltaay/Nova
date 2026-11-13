import { describe, expect, it } from 'vitest';
import { monthGrid } from '../account/accountCalendar';
import type { EquityPoint, HistoryDaily, PracticeHistory } from '../account/accountHistoryTypes';
import { daySeries, phoneMonth } from './phoneCalendar';

const row = (date: string, realized: number): HistoryDaily => ({ date, realized, commissions: 1, fees: 0, fills: 2, archived: false });
// 15:00 UTC is 10:00 or 11:00 ET: inside the practice day of its own date.
const ts = (date: string, minute = 0): number => Date.parse(`${date}T15:${String(minute).padStart(2, '0')}:00Z`) / 1000;
const point = (t: number, realized: number, unrealized = 0): EquityPoint => ({ ts: t, net_liquidation: 0, cash: 0, realized, unrealized });

describe('phoneMonth', () => {
  it('shows Monday to Friday, and leaves out a week with no weekday of the month', () => {
    // November 2026 starts on a Sunday; its last day is Monday the 30th.
    const month = phoneMonth(monthGrid(2026, 10, [row('2026-11-10', 640)], '2026-11-13'));
    expect(month.columns).toBe(5);
    expect(month.cells.length).toBe(25);
    expect(month.cells.slice(0, 5).map((c) => c.day)).toEqual([2, 3, 4, 5, 6]);
    expect(month.cells.slice(20).map((c) => c.day)).toEqual([30, null, null, null, null]);
    expect(month.cells.find((c) => c.day === 13)?.today).toBe(true);
  });

  it('drops a first week that holds only a weekend', () => {
    // August 2026 starts on a Saturday.
    const month = phoneMonth(monthGrid(2026, 7, [], '2026-08-03'));
    expect(month.cells[0].day).toBe(3);
  });

  it('shows all seven days when a weekend traded, so no figure is hidden', () => {
    const month = phoneMonth(monthGrid(2026, 10, [row('2026-11-07', -20)], '2026-11-13'));
    expect(month.columns).toBe(7);
    expect(month.cells.find((c) => c.day === 7)?.pnl).toBe(-20);
  });
});

describe('daySeries', () => {
  const history = {
    equity: [
      point(ts('2026-11-09'), 87),
      point(ts('2026-11-10', 1), 87, 40),
      point(ts('2026-11-10', 5), 300),
      point(ts('2026-11-11'), 245),
    ],
  } as PracticeHistory;

  it('starts the day at zero and counts only that day', () => {
    expect(daySeries(history, '2026-11-10').map((p) => p.value)).toEqual([0, 40, 213]);
  });

  it('counts the first day of the ledger from zero', () => {
    expect(daySeries(history, '2026-11-09').map((p) => p.value)).toEqual([0, 87]);
  });

  it('is empty for a day the history has no point for', () => {
    expect(daySeries(history, '2026-11-12')).toEqual([]);
  });
});
