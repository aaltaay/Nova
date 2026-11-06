import { describe, expect, it } from 'vitest';
import type { PracticeAccount, PracticeOwnerHolding, PracticePosition } from '../practice';
import { botsBook, botsRowsFor, deskPositions } from './deskPositions';
import type { IbkrPosition } from './types';

const holder = (bot: string | null, qty: number, avg_cost = 125.9, unrealized_pnl = 19.19): PracticeOwnerHolding => ({
  owner: bot ? 'bots' : 'you', bot, qty, avg_cost, unrealized_pnl,
});

const held = (symbol: string, mark: number | null, by_owner: PracticeOwnerHolding[]): PracticePosition => ({
  symbol, mark, avg_cost: 125.9, unrealized: 0, by_owner, qty: by_owner.reduce((n, h) => n + h.qty, 0),
});

const paper = (positions: PracticePosition[]): PracticeAccount => ({ positions, books: {} } as unknown as PracticeAccount);

const yours = (symbol: string, qty: number): IbkrPosition => ({
  symbol, qty, avg_cost: 10, market_price: 11, market_value: qty * 11, unrealized_pnl: qty, realized_pnl: 0,
});

describe('deskPositions', () => {
  it("lists a stock only the bots hold, at the bot's own cost and open P&L (2026-11-04, Positions 0)", () => {
    const rows = deskPositions([], paper([held('ORCL', 124.89, [holder('live_trader', -19)])]));
    expect(rows).toEqual([{
      symbol: 'ORCL', qty: -19, avg_cost: 125.9, market_price: 124.89, market_value: -19 * 124.89,
      unrealized_pnl: 19.19, realized_pnl: null, position_side: 'short', owner: 'bots', bot: 'live_trader', bots_qty: -19,
    }]);
  });

  it('keeps your row exactly as it came, and says whose it is', () => {
    const mine = yours('INTC', 100);
    const rows = deskPositions([mine], paper([held('INTC', 11, [holder(null, 100), holder('live_trader', 40)])]));
    expect(rows[0]).toEqual({ ...mine, owner: 'you', bot: null });
    expect(rows.slice(1).map((r) => [r.symbol, r.qty, r.bot])).toEqual([['INTC', 40, 'live_trader']]);
    expect(mine).not.toHaveProperty('owner');
  });

  it('gives each bot in one stock its own row, and each row the whole book the Close sells', () => {
    const rows = deskPositions([], paper([held('ORCL', 124, [holder('live_trader', -19), holder('claude', -5)])]));
    expect(rows.map((r) => [r.bot, r.qty, r.bots_qty])).toEqual([['live_trader', -19, -24], ['claude', -5, -24]]);
  });

  it("never lists Auto-entry's shares twice: they are already on your row, and the chip names it", () => {
    const rows = deskPositions([yours('GENK', 50)], paper([held('GENK', 11, [holder('auto_entry', 50)])]));
    expect(rows.map((r) => [r.symbol, r.qty, r.owner, r.bot])).toEqual([['GENK', 50, 'you', 'auto_entry']]);
  });

  it('says You on a row that mixes your shares and Auto-entry\'s', () => {
    const rows = deskPositions([yours('GENK', 60)], paper([held('GENK', 11, [holder(null, 10), holder('auto_entry', 50)])]));
    expect(rows.map((r) => [r.qty, r.owner, r.bot])).toEqual([[60, 'you', null]]);
  });

  it('prices nothing it has no mark for', () => {
    const [row] = deskPositions([], paper([held('ORCL', null, [holder('live_trader', -19)])]));
    expect(row.market_value).toBeNull();
    expect(row.market_price).toBeNull();
  });

  it('hands your rows back untouched where there is one book', () => {
    const mine = [yours('INTC', 100)];
    expect(deskPositions(mine, null)).toBe(mine);
    expect(deskPositions(mine, { positions: [held('INTC', 11, [holder(null, 100)])] } as unknown as PracticeAccount)).toBe(mine);
  });

  it('survives a positions: null answer', () => {
    expect(deskPositions([], { positions: null, books: {} } as unknown as PracticeAccount)).toEqual([]);
  });
});

describe('botsBook', () => {
  it("adds every bot's shares per stock, Auto-entry's with the rest; yours never count", () => {
    const book = botsBook(paper([held('ORCL', 124, [holder(null, 7), holder('live_trader', -19), holder('auto_entry', -5)])]));
    expect([...book]).toEqual([['ORCL', -24]]);
  });

  it('is empty off Paper', () => {
    expect(botsBook(null).size).toBe(0);
  });
});

describe('botsRowsFor', () => {
  it("finds one stock's bots' rows, whatever the case", () => {
    const rows = deskPositions([yours('ORCL', 1)], paper([
      held('ORCL', 124, [holder(null, 1), holder('live_trader', -19)]),
      held('INTC', 58, [holder('live_trader', 40)]),
    ]));
    expect(botsRowsFor(rows, ' orcl ').map((r) => r.qty)).toEqual([-19]);
  });
});
