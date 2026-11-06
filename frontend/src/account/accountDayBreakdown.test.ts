/**
 * The Calendar's day breakdown: the day's totals are the history's `daily`
 * rows, its stocks and trades this ledger's fills. A trade is one stock from
 * flat back to flat and counts on the day it closes.
 */
import { describe, expect, it } from 'vitest';
import { dayBreakdowns, fillDay, monthDayTotals, roundTrips } from './accountDayBreakdown';
import { paperHistoryFixture } from './accountFixtures';
import type { HistoryFill } from './accountHistoryTypes';

// Fri 2026-09-18 10:00 ET: the fixture's six fills land between 09:00 and 09:57 ET that day.
const PLAYHEAD = Date.parse('2026-09-18T10:00:00-04:00') / 1000;

const fill = (iso: string, symbol: string, side: 'BUY' | 'SELL', qty: number, price: number, realized: number, source = 'manual'): HistoryFill => ({
  ts: Date.parse(iso) / 1000, order_id: 1, symbol, side, qty, price, source, bot_id: null,
  commission: 1, fees: 0, realized, fill_estimated: true, fill_basis: 'quote',
});

describe('dayBreakdowns', () => {
  const days = dayBreakdowns(paperHistoryFixture(PLAYHEAD));

  it("reads the day's totals from its daily row: net, gross before costs, commissions, fees, fills", () => {
    const day = days.get('2026-09-18')!;
    expect(day.net).toBeCloseTo(87.1, 6);
    expect(day.gross).toBeCloseTo(97.5, 6);
    expect(day.commissions).toBe(10);
    expect(day.fees).toBeCloseTo(0.4, 6);
    expect(day.fills).toBe(6);
    expect(day.detailed).toBe(true);
    expect(day.partial).toBe(false);
  });

  it('counts closed round trips, won and lost after costs, and leaves the open position out', () => {
    const day = days.get('2026-09-18')!;
    expect(day.trades.map((t) => [t.symbol, t.side, t.shares, t.bot])).toEqual([
      ['GRML', 'long', 500, false],
      ['QNME', 'long', 250, true],
    ]);
    expect(day.trades[0].net).toBeCloseTo(119.8, 6);
    expect(day.trades[1].net).toBeCloseTo(-30.2, 6);
    expect([day.won, day.lost]).toEqual([1, 1]);
    expect(day.botFills).toBe(2);
    expect([day.sharesBought, day.sharesSold]).toEqual([1150, 750]);
  });

  it('lists every stock the day touched, worst net first, with its average buy and sell', () => {
    const [qnme, grml] = days.get('2026-09-18')!.stocks;
    expect(qnme.symbol).toBe('QNME');
    expect(qnme.net).toBeCloseTo(-30.2, 6);
    expect(grml).toMatchObject({ symbol: 'GRML', trades: 1, fills: 4, bought: 900, sold: 500 });
    expect(grml.avgBuy).toBeCloseTo((500 * 5.1 + 300 * 8.75 + 100 * 8.8) / 900, 6);
    expect(grml.avgSell).toBeCloseTo(5.35, 6);
    expect(grml.commission).toBeCloseTo(7.5, 6);
  });

  it("states an archived ledger's day as totals only, never invented stocks", () => {
    const day = days.get('2026-09-10')!;
    expect(day).toMatchObject({ archived: true, detailed: false, fills: 2, trades: [], stocks: [] });
    expect(day.gross).toBeCloseTo(98.55, 6);
  });

  it('marks a day an archived ledger shared with this one as partial', () => {
    const history = paperHistoryFixture(PLAYHEAD);
    history.daily.push({ date: '2026-09-18', realized: -5, commissions: 1, fees: 0, fills: 1, archived: true });
    const day = dayBreakdowns(history).get('2026-09-18')!;
    expect(day).toMatchObject({ detailed: true, partial: true, fills: 7 });
    expect(day.net).toBeCloseTo(82.1, 6);
  });
});

describe('roundTrips', () => {
  it('counts a trade held overnight on the day it closes', () => {
    const fills = [
      fill('2026-10-16T15:00:00-04:00', 'ABC', 'BUY', 100, 2, -1),
      fill('2026-10-19T10:00:00-04:00', 'ABC', 'SELL', 100, 2.5, 49),
    ];
    const history = {
      fills,
      daily: [
        { date: '2026-10-16', realized: -1, commissions: 1, fees: 0, fills: 1, archived: false },
        { date: '2026-10-19', realized: 49, commissions: 1, fees: 0, fills: 1, archived: false },
      ],
    };
    const days = dayBreakdowns(history);
    expect(days.get('2026-10-16')!.trades).toEqual([]);
    expect(days.get('2026-10-16')!.stocks[0]).toMatchObject({ symbol: 'ABC', bought: 100, sold: 0, trades: 0 });
    expect(days.get('2026-10-19')!.trades.map((t) => [t.symbol, t.net])).toEqual([['ABC', 48]]);
    expect(fillDay(fills[1].ts)).toBe('2026-10-19');
  });

  it('closes a short on its cover and opens the other side when a fill crosses flat', () => {
    const trades = roundTrips([
      fill('2026-10-19T10:00:00-04:00', 'XYZ', 'SELL', 100, 5, -1),
      fill('2026-10-19T10:05:00-04:00', 'XYZ', 'BUY', 150, 4.9, 9),
      fill('2026-10-19T10:09:00-04:00', 'XYZ', 'SELL', 50, 5, 4),
    ]);
    expect(trades.map((t) => [t.side, t.shares, t.fills, t.net])).toEqual([
      ['short', 100, 2, 8],
      ['long', 50, 1, 4],
    ]);
  });
});

describe('monthDayTotals', () => {
  it("sums the month's days and says how many list no trades", () => {
    const days = dayBreakdowns(paperHistoryFixture(PLAYHEAD));
    const total = monthDayTotals(days, ['2026-09-10', '2026-09-18', '2026-09-19']);
    expect(total.commissions).toBe(12);
    expect(total.fills).toBe(8);
    expect([total.trades, total.won, total.lost, total.incompleteDays]).toEqual([2, 1, 1, 1]);
    expect(total.gross).toBeCloseTo(97.5 + 98.55, 6);
  });

  it("counts a day an archived ledger shared as incomplete: its commissions are in, its trades are not", () => {
    const history = paperHistoryFixture(PLAYHEAD);
    history.daily = history.daily.filter((r) => !r.archived);
    expect(monthDayTotals(dayBreakdowns(history), ['2026-09-18']).incompleteDays).toBe(0);
    history.daily.push({ date: '2026-09-18', realized: -102, commissions: 100, fees: 0, fills: 2, archived: true });
    const total = monthDayTotals(dayBreakdowns(history), ['2026-09-18']);
    expect([total.commissions, total.trades, total.incompleteDays]).toEqual([110, 2, 1]);
  });
});
