import { describe, expect, it } from 'vitest';
import { monthGrid, monthLabel, parseIsoDate, shiftMonth } from './accountCalendar';
import type { HistoryDaily } from './accountHistoryTypes';

// realized is net of commissions and fees, as GET /api/practice/history sends it.
const DAILY: HistoryDaily[] = [
  { date: '2026-09-10', realized: 94.15, commissions: 2, fees: 0.2, fills: 2, archived: true },
  { date: '2026-09-18', realized: 83.5, commissions: 1, fees: 0.1, fills: 1, archived: true },
  { date: '2026-09-18', realized: 9, commissions: 1, fees: 0, fills: 1, archived: false },
  { date: '2026-09-21', realized: 87.1, commissions: 10, fees: 0.4, fills: 6, archived: false },
  { date: '2026-10-01', realized: 4, commissions: 1, fees: 0, fills: 1, archived: false },
];

describe('monthGrid', () => {
  it('maps daily rows onto September 2026 with weekday offset, weekends, today and archived days', () => {
    const grid = monthGrid(2026, 8, DAILY, '2026-09-21');
    // Sep 1 2026 is a Tuesday -> two leading blanks, 30 days, padded to full weeks.
    expect(grid.cells.slice(0, 2).every((c) => c.day == null)).toBe(true);
    expect(grid.cells.length % 7).toBe(0);
    const byDay = new Map(grid.cells.filter((c) => c.day != null).map((c) => [c.day!, c]));
    expect(byDay.size).toBe(30);
    expect(byDay.get(5)!.weekend).toBe(true);
    expect(byDay.get(6)!.weekend).toBe(true);
    expect(byDay.get(7)!.weekend).toBe(false);
    expect(byDay.get(7)!.pnl).toBeNull();
    const d10 = byDay.get(10)!;
    expect(d10.archived).toBe(true);
    expect(d10.pnl).toBeCloseTo(94.15, 6); // the day's net, never costs subtracted twice (QA V1)
    // A reset mid-day: two rows on one date sum, and the cell is not "archived".
    const d18 = byDay.get(18)!;
    expect(d18.archived).toBe(false);
    expect(d18.pnl).toBeCloseTo(83.5 + 9, 6);
    expect(d18.fills).toBe(2);
    const d21 = byDay.get(21)!;
    expect(d21.today).toBe(true);
    expect(d21.pnl).toBeCloseTo(87.1, 6);
    expect(grid.archivedTotal).toBeCloseTo(94.15 + 83.5, 6);
    expect(grid.currentTotal).toBeCloseTo(9 + 87.1, 6);
    expect(grid.rows).toBe(4);
  });

  it('an empty month has no rows and zero totals; October holds its own row', () => {
    const empty = monthGrid(2026, 7, DAILY, '2026-09-21');
    expect(empty.rows).toBe(0);
    expect(empty.currentTotal).toBe(0);
    const oct = monthGrid(2026, 9, DAILY, '2026-09-21');
    expect(oct.rows).toBe(1);
    expect(oct.cells.some((c) => c.today)).toBe(false);
  });

  it('shifts months across year boundaries and labels them', () => {
    expect(shiftMonth(2026, 0, -1)).toEqual({ year: 2025, month: 11 });
    expect(shiftMonth(2026, 11, 1)).toEqual({ year: 2027, month: 0 });
    expect(monthLabel(2026, 8)).toBe('September 2026');
    expect(parseIsoDate('2026-09-21')).toEqual({ year: 2026, month: 8, day: 21 });
    expect(parseIsoDate('nope')).toBeNull();
  });
});
