import { describe, expect, it } from 'vitest';
import type { LeaderboardDay } from '../leaderboard/leaderboardTypes';
import { cellTitle, dayFacts, monthGrid, monthRange, shiftMonth } from './simDayCalendarModel';
import type { CaptureSessions } from './useSimSessionController';

const summary = { minutes: 960, first_ts: 1, last_ts: 2 };
const DAYS: LeaderboardDay[] = [
  { date: '2026-09-21', recorded: { ...summary, boards: ['gainers'] }, reconstructed: summary },
  { date: '2026-09-18', recorded: null, reconstructed: summary },
  { date: '2021-09-21', recorded: null, reconstructed: summary },
];
const SESSIONS: CaptureSessions = {
  days: [],
  tickers_by_day: {
    '2026-09-22': [{ symbol: 'GRML', prints: 5, l2: 1, usable: true }],
    '2026-09-21': [{ symbol: 'GRML', prints: 5, l2: 1 }, { symbol: 'AAPL', prints: 5, l2: 1 }],
    '2026-09-19': [{ symbol: 'IMCC', prints: 5, l2: 1, usable: true }],
    '2026-09-17': [{ symbol: 'EMPTY', prints: 0, l2: 0, usable: false, empty: true }],
  },
};
const LABELS = {
  rebuilt: 'rebuilt', recorded: 'recorded', sessions: (s: string[]) => `records: ${s.join(', ')}`,
  nothing: 'nothing', closed: 'closed',
};

describe('dayFacts', () => {
  it('keeps each source apart and lists only usable Session Records', () => {
    const facts = dayFacts(DAYS, SESSIONS);
    expect(facts.get('2026-09-21')).toEqual({ rebuilt: true, recorded: true, sessions: ['AAPL', 'GRML'] });
    expect(facts.get('2026-09-18')).toEqual({ rebuilt: true, recorded: false, sessions: [] });
    expect(facts.get('2026-09-22')).toEqual({ rebuilt: false, recorded: false, sessions: ['GRML'] });
    expect(facts.has('2026-09-17')).toBe(false);
  });
});

describe('monthGrid', () => {
  const facts = dayFacts(DAYS, SESSIONS);
  const cells = monthGrid({ year: 2026, month0: 8 }, facts, '2026-09-22', '2026-09-18').flat();
  const cell = (date: string) => cells.find(c => c.date === date)!;

  it('runs Sunday first in whole weeks, padded with the neighbouring months', () => {
    expect(cells.length % 7).toBe(0);
    expect(cells[0].date).toBe('2026-08-30');
    expect(cell('2026-08-31').inMonth).toBe(false);
    expect(cell('2026-09-01').inMonth).toBe(true);
  });

  it('lets only an exchange day with something on file be picked, today included', () => {
    expect(cell('2026-09-21').selectable).toBe(true);
    expect(cell('2026-09-22').selectable && cell('2026-09-22').today).toBe(true);
    expect(cell('2026-09-16').selectable).toBe(false); // nothing on file
    expect(cell('2026-09-19').selectable).toBe(false); // a Saturday recording cannot be opened
    expect(cell('2026-09-18').selected).toBe(true);
  });

  it('titles a day with each fact from its own source', () => {
    expect(cellTitle(cell('2026-09-21'), LABELS)).toBe('2026-09-21\nrecorded\nrecords: AAPL, GRML\nrebuilt');
    expect(cellTitle(cell('2026-09-16'), LABELS)).toBe('2026-09-16\nnothing');
    expect(cellTitle(cell('2026-09-19'), LABELS)).toBe('2026-09-19\nrecords: IMCC\nclosed');
  });
});

describe('month navigation', () => {
  it('reaches from the oldest day on file to today', () => {
    expect(monthRange(dayFacts(DAYS, null), '2026-09-22')).toEqual({
      first: { year: 2021, month0: 8 }, last: { year: 2026, month0: 8 },
    });
    expect(shiftMonth({ year: 2026, month0: 0 }, -1)).toEqual({ year: 2025, month0: 11 });
    expect(shiftMonth({ year: 2025, month0: 11 }, 1)).toEqual({ year: 2026, month0: 0 });
  });
});

describe('calendarPlacement', () => {
  it('sits under its button, inside the window, and flips up when the bottom is short', async () => {
    const { calendarPlacement } = await import('./SimDayPicker');
    const view = { width: 1500, height: 950 };
    expect(calendarPlacement({ top: 60, bottom: 82, left: 600 }, view)).toEqual({ top: 86, left: 600 });
    expect(calendarPlacement({ top: 60, bottom: 82, left: 1400 }, view).left).toBe(1500 - 248 - 8);
    expect(calendarPlacement({ top: 800, bottom: 822, left: 600 }, view)).toEqual({ top: 800 - 300 - 4, left: 600 });
  });
});
