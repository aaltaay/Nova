/**
 * @vitest-environment jsdom
 *
 * A calendar day, by trader (ADR 072, mockup three-books v1 item 5, approved 2026-11-14): under the day's Net one
 * line per trader that traded that day, in the order You, Claude, The brain, Earlier bots; a colour bar along the
 * cell's foot, each colour as wide as that trader's share of the day; the month's foot lists all four; the hover
 * card lists each trader that traded with its P&L and its trades.
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { dayBreakdowns, ownerDayTrades } from './accountDayBreakdown';
import { threeBooksHistoryFixture } from './accountFixtures';
import { CalendarPanel, shareWidths } from './CalendarPanel';
import { daySplits } from './ownerView';

afterEach(cleanup);

// Fri 2026-09-18 10:00 ET: today you and Claude traded; on Wed 2026-09-16 only the Live Trader (Earlier bots).
const PLAYHEAD = Date.parse('2026-09-18T10:00:00-04:00') / 1000;
const history = threeBooksHistoryFixture(PLAYHEAD);
const days = dayBreakdowns(history);
const split = daySplits(history);

const panel = (withSplit = true) => (
  <CalendarPanel history={history} absence={null} today="2026-09-18" days={days} selected={null} onSelect={() => {}}
    split={withSplit ? split : null} />
);
const cell = (date: string) => screen.getByTestId(`account-calendar-day-${date}`);
const owners = (el: HTMLElement, selector: string) =>
  [...el.querySelectorAll(selector)].map((n) => n.getAttribute('data-owner'));

describe('a calendar day, by trader', () => {
  it("lists one line per trader that traded, in the books' order, under the day's Net", () => {
    render(panel());
    const today = within(cell('2026-09-18')).getByTestId('account-calendar-split');
    expect(owners(today, '.acct-cal__o')).toEqual(['you', 'claude']);
    expect(today.textContent).toBe('+$2+$66');
    const wed = within(cell('2026-09-16')).getByTestId('account-calendar-split');
    expect(owners(wed, '.acct-cal__o')).toEqual(['earlier_bots']);
  });

  it("runs the colour bar along the foot, each colour as wide as that trader's share", () => {
    render(panel());
    const bar = within(cell('2026-09-18')).getByTestId('account-calendar-share');
    const parts = [...bar.querySelectorAll('i')];
    expect(parts.map((p) => p.getAttribute('data-owner'))).toEqual(['you', 'claude']);
    expect(Number(parts[0].style.flex.split(' ')[0])).toBeCloseTo(1.98 / 67.78, 4);
    expect(Number(parts[1].style.flex.split(' ')[0])).toBeCloseTo(65.8 / 67.78, 4);
    expect(cell('2026-09-18').className).toMatch(/has-split/);
    // By size, whatever the sign: a loss takes its share too.
    expect(shareWidths({ you: 30, claude: -10, brain: 0, earlier_bots: 0 })).toEqual([['you', 0.75], ['claude', 0.25]]);
    expect(shareWidths({ you: 0, claude: 0, brain: 0, earlier_bots: 0 })).toEqual([]);
  });

  it('lists all four books in the month\'s foot, always, in the same order', () => {
    render(panel());
    const foot = screen.getByTestId('account-calendar-month-split');
    expect(owners(foot, '[data-owner]')).toEqual(['you', 'claude', 'brain', 'earlier_bots']);
    expect(foot.textContent).toBe(' ·  You +$1.98 ·  Claude +$65.80 ·  The brain $0.00 ·  Earlier bots +$8.99');
  });

  it('names each trader that traded on the hover card, with its P&L and its trades', () => {
    render(panel());
    fireEvent.mouseEnter(cell('2026-09-18'));
    const rows = screen.getByTestId('account-calendar-card-traders');
    expect(owners(rows, '[data-owner]')).toEqual(['you', 'claude']);
    expect(rows.textContent).toBe('You+$1.98 · 1 tradeClaude+$65.80 · 2 trades');
  });

  it("counts each trader's own trades: Claude's VTSI you closed is Claude's", () => {
    const trades = ownerDayTrades(history.fills);
    expect(trades?.get('2026-09-18')).toEqual({ you: 1, claude: 2, brain: 0, earlier_bots: 0 });
    expect(trades?.get('2026-09-16')).toEqual({ you: 0, claude: 0, brain: 0, earlier_bots: 1 });
  });

  it('a view of one book keeps the plain day: no trader lines, no bar', () => {
    render(panel(false));
    expect(within(cell('2026-09-18')).queryByTestId('account-calendar-split')).toBeNull();
    expect(within(cell('2026-09-18')).queryByTestId('account-calendar-share')).toBeNull();
    expect(screen.queryByTestId('account-calendar-month-split')).toBeNull();
  });
});
