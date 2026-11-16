import { describe, expect, it } from 'vitest';
import type { PracticeAccount, PracticeOwnerHolding, PracticePosition } from '../practice';
import { deskPositions, isOthersRow, othersBook, othersRowsFor, ownShares } from './deskPositions';
import type { IbkrPosition } from './types';

const holder = (owner: PracticeOwnerHolding['owner'], qty: number, extra: Partial<PracticeOwnerHolding> = {}): PracticeOwnerHolding => ({
  owner, bot: owner === 'earlier_bots' ? 'live_trader' : null, qty, avg_cost: 125.9, unrealized_pnl: 19.19, ...extra,
});

const held = (symbol: string, mark: number | null, by_owner: PracticeOwnerHolding[]): PracticePosition => ({
  symbol, mark, avg_cost: 125.9, unrealized: 0, by_owner, qty: by_owner.reduce((n, h) => n + h.qty, 0),
});

const books = (positions: PracticePosition[]): PracticeAccount => ({ positions, books: {} } as unknown as PracticeAccount);

const yours = (symbol: string, qty: number, extra: Partial<IbkrPosition> = {}): IbkrPosition => ({
  symbol, qty, avg_cost: 10, market_price: 11, market_value: qty * 11, unrealized_pnl: qty, realized_pnl: 0, ...extra,
});

describe('deskPositions (ADR 072)', () => {
  it("lists a stock only Claude holds, at Claude's own cost and open P&L", () => {
    const rows = deskPositions([], books([held('ORCL', 124.89, [holder('claude', -19)])]));
    expect(rows).toEqual([{
      symbol: 'ORCL', qty: -19, avg_cost: 125.9, market_price: 124.89, market_value: -19 * 124.89,
      unrealized_pnl: 19.19, realized_pnl: null, position_side: 'short', owner: 'claude', bot: null,
    }]);
  });

  it('keeps your row exactly as it came, and says whose it is', () => {
    const mine = yours('INTC', 100);
    const rows = deskPositions([mine], books([held('INTC', 11, [holder('you', 100), holder('brain', 40)])]));
    expect(rows[0]).toEqual({ ...mine, owner: 'you', bot: null });
    expect(rows.slice(1).map((r) => [r.symbol, r.qty, r.owner])).toEqual([['INTC', 40, 'brain']]);
    expect(mine).not.toHaveProperty('owner');
  });

  it('gives each trader in one stock its own row, a retired bot by its name', () => {
    const rows = deskPositions([], books([held('ORCL', 124, [holder('claude', -19), holder('earlier_bots', -5)])]));
    expect(rows.map((r) => [r.owner, r.bot, r.qty])).toEqual([['claude', null, -19], ['earlier_bots', 'live_trader', -5]]);
  });

  it('never lists handed shares twice: they are already on your row, which says how many', () => {
    const mine = yours('XLAB', 200, { handed_qty: 200, handed_from: 'brain' });
    const rows = deskPositions([mine], books([held('XLAB', 4.53, [holder('brain', 200, { handed: true })])]));
    expect(rows.map((r) => [r.symbol, r.qty, r.owner, r.handed_from])).toEqual([['XLAB', 200, 'you', 'brain']]);
    expect(ownShares(rows[0])).toBe(0);
  });

  it('prices nothing it has no mark for', () => {
    const [row] = deskPositions([], books([held('ORCL', null, [holder('claude', -19)])]));
    expect(row.market_value).toBeNull();
    expect(row.market_price).toBeNull();
  });

  it('hands your rows back untouched where there is one book', () => {
    const mine = [yours('INTC', 100)];
    expect(deskPositions(mine, null)).toBe(mine);
    expect(deskPositions(mine, { positions: [held('INTC', 11, [holder('you', 100)])] } as unknown as PracticeAccount)).toBe(mine);
  });

  it('survives a positions: null answer', () => {
    expect(deskPositions([], { positions: null, books: {} } as unknown as PracticeAccount)).toEqual([]);
  });
});

describe('othersBook', () => {
  it("adds each other trader's own shares per stock, the biggest first; yours and handed shares never count", () => {
    const book = othersBook(books([held('ORCL', 124, [
      holder('you', 7), holder('claude', -5), holder('brain', 30), holder('earlier_bots', 12, { handed: true }),
    ])]));
    expect([...book]).toEqual([['ORCL', [{ owner: 'brain', qty: 30 }, { owner: 'claude', qty: -5 }]]]);
  });

  it('is empty without books, and leaves out a stock only you hold', () => {
    expect(othersBook(null).size).toBe(0);
    expect(othersBook(books([held('INTC', 11, [holder('you', 100)])])).size).toBe(0);
  });
});

describe('othersRowsFor', () => {
  it("finds one stock's other traders' rows, whatever the case", () => {
    const rows = deskPositions([yours('ORCL', 1)], books([
      held('ORCL', 124, [holder('you', 1), holder('claude', -19)]),
      held('INTC', 58, [holder('brain', 40)]),
    ]));
    expect(othersRowsFor(rows, ' orcl ').map((r) => [r.owner, r.qty])).toEqual([['claude', -19]]);
    expect(rows.map(isOthersRow)).toEqual([false, true, true]);
  });
});
