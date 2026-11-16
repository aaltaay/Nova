/**
 * @vitest-environment jsdom
 *
 * Three books, one account (ADR 072, mockup three-books v1 items 2-4): the three cards, Earlier bots' slim line
 * only while it has a number, each AI trader's own budget, the per-book split under Day's P&L and Fills today, and
 * P&L by day with a bar per book and the All line.
 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { threeBooksHistoryFixture, THREE_BOOKS_ACCOUNT } from './accountFixtures';
import { BookSplitMini, BooksCards, bookRows } from './BooksCards';
import { DayBars } from './DayBars';
import { ALL_VIEW, emptySplit, viewHistory } from './ownerView';

afterEach(cleanup);

const books = THREE_BOOKS_ACCOUNT.books!;
const month = { you: 539.54, claude: -102.19, brain: 0, earlier_bots: -871.91 };
const cards = (over: Partial<Parameters<typeof BooksCards>[0]> = {}) => (
  <BooksCards books={books} view={ALL_VIEW} month={month} monthName="Nov" traded={new Set(['you', 'claude', 'earlier_bots'] as const)}
    hidden={false} hiddenText="••••" {...over} />
);

describe('BooksCards', () => {
  it("draws You, Claude and The brain with today's P&L and the month; a trader that never traded says so", () => {
    render(cards());
    expect(screen.getByTestId('account-books').textContent).toContain('Three books, one account');
    expect(screen.getByTestId('account-book-you').textContent).toBe('You+$19.98todayNov +$539.54');
    expect(screen.getByTestId('account-book-claude').textContent).toBe('Claude+$63.76todayNov -$102.19');
    expect(screen.getByTestId('account-book-brain').textContent).toBe('The brain$0.00todayno trades yet');
  });

  it('shows Earlier bots as a slim line, history only, while it has a number this month', () => {
    render(cards());
    expect(screen.getByTestId('account-book-earlier_bots').textContent).toBe('Earlier botsNov -$871.91history only');
    cleanup();
    render(cards({ month: { ...month, earlier_bots: 0 } }));
    expect(screen.queryByTestId('account-book-earlier_bots')).toBeNull();
  });

  it("states each AI trader's own budget, its meter in its own colour; the bots' single budget is gone", () => {
    render(cards());
    expect(screen.getByTestId('account-budgets').textContent).toContain("Each trader's own budget");
    expect(screen.getByTestId('account-budget-claude').textContent).toBe("Claude's budget$592.11 of $25,000.00 held");
    expect(screen.getByTestId('account-budget-brain').textContent).toBe("The brain's budget$0.00 of $25,000.00 held");
    expect(within(screen.getByTestId('account-budget-claude')).getByRole('meter').className).toBe('acct-budget__meter is-claude');
    expect(screen.queryByTestId('account-bots-budget')).toBeNull();
  });

  it('dims the cards the view does not show', () => {
    render(cards({ view: { book: 'claude', bot: null } }));
    expect(screen.getByTestId('account-book-claude').className).not.toMatch(/is-dim/);
    expect(screen.getByTestId('account-book-you').className).toMatch(/is-dim/);
    expect(screen.getByTestId('account-book-earlier_bots').className).toMatch(/is-dim/);
  });

  it("splits Day's P&L and Fills today by book; Earlier bots only with a number", () => {
    const rows = bookRows(books);
    expect(rows.dayPnl).toEqual({ you: 19.98, claude: 63.76, brain: 0, earlier_bots: 0 });
    expect(rows.fills).toEqual({ you: 2, claude: 4, brain: 0, earlier_bots: 0 });
    render(<><BookSplitMini split={rows.dayPnl} money testId="day" /><BookSplitMini split={rows.fills} money={false} testId="fills" /></>);
    expect(screen.getByTestId('day').textContent).toBe('+$19.98+$63.76$0.00');
    expect(screen.getByTestId('fills').textContent).toBe('240');
    cleanup();
    render(<BookSplitMini split={{ ...emptySplit(), earlier_bots: -3 }} money testId="day" />);
    expect([...screen.getByTestId('day').querySelectorAll('[data-owner]')].map((n) => n.getAttribute('data-owner')))
      .toEqual(['you', 'claude', 'brain', 'earlier_bots']);
  });
});

describe('DayBars (P&L by day)', () => {
  const history = threeBooksHistoryFixture(Date.parse('2026-09-18T10:00:00-04:00') / 1000);

  it('draws a bar per book that traded each day, and the All line; the legend totals each book', () => {
    render(<DayBars daily={history.daily} view={ALL_VIEW} />);
    const owners = (date: string) => [...screen.getByTestId(`account-day-bar-${date}`).querySelectorAll('rect')]
      .map((r) => r.getAttribute('data-owner'));
    expect(owners('2026-09-18')).toEqual(['you', 'claude']);
    expect(owners('2026-09-16')).toEqual(['earlier_bots']);
    expect(screen.getByTestId('account-day-legend').textContent)
      .toBe('You+$1.98Claude+$65.80The brain$0.00Earlier bots+$8.99All+$76.77');
    expect(document.querySelector('.acct-daybars__all')).toBeTruthy();
  });

  it("a view of one book draws that book's bars alone, no All line", () => {
    const claude = viewHistory(history, { book: 'claude', bot: null })!;
    render(<DayBars daily={claude.daily} view={{ book: 'claude', bot: null }} />);
    expect(screen.getByTestId('account-day-legend').textContent).toBe('Claude+$65.80');
    expect([...document.querySelectorAll('.acct-daybars rect')].map((r) => r.getAttribute('data-owner'))).toEqual(['claude']);
    expect(document.querySelector('.acct-daybars__all')).toBeNull();
  });
});
