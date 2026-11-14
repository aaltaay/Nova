/**
 * The sample Paper ledger keeps the three traders' books (ADR 072): Nova Marketing Sample Data whose books add up
 * to the account's, to the cent, on every day and over the range.
 */
import { describe, expect, it } from 'vitest';
import { practiceAccount } from './desk';
import { practiceHistory } from './pages';
import { BOOKS } from './practiceBooks';

describe('the sample ledger by book', () => {
  it("the four books' day adds up to the account's; the brain has not traded", () => {
    const account = practiceAccount('paper');
    const books = account.books;
    expect(BOOKS.reduce((s, b) => s + books[b].day_pnl, 0)).toBeCloseTo(account.day_pnl, 6);
    expect(BOOKS.reduce((s, b) => s + books[b].fills_today, 0)).toBe(account.fills_today);
    expect(books.brain).toMatchObject({ day_pnl: 0, fills_today: 0, budget_usd: 25_000, budget_used_usd: 0 });
    expect(practiceAccount('sim').books.you.day_pnl).toBe(0);
  });

  it("every daily row's books add up to the row, and every range's components to its realized", () => {
    for (const range of ['1D', 'ALL']) {
      const h = practiceHistory(range, 'paper');
      for (const row of h.daily) {
        expect(BOOKS.reduce((s, b) => s + row[b].realized, 0)).toBeCloseTo(row.realized, 6);
      }
      const c = h.components;
      expect(c.you_realized + c.claude_realized + c.brain_realized + c.earlier_bots_realized).toBeCloseTo(c.realized, 6);
      const last = h.equity[h.equity.length - 1];
      expect(last.you_pnl + last.claude_pnl + last.brain_pnl + last.earlier_bots_pnl).toBeCloseTo(last.realized, 6);
      expect(h.fills.every((f) => f.parts.length === 1 && f.parts[0].owner === f.owner)).toBe(true);
    }
    expect(practiceHistory('ALL', 'paper').by_owner.map((r) => r.owner)).toEqual(['you', 'claude', 'earlier_bots']);
  });
});
