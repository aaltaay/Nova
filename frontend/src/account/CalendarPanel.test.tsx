/**
 * @vitest-environment jsdom
 *
 * The calendar shows today's month and moves with it. `today` changes under a
 * mounted panel: on Sim the page reads the browser's clock until the Sim clock
 * answers, then the replay playhead's day (C20 / V32). The panel used to keep
 * the month of its first render, so from 2026-10-01 a replayed Sep 18 opened on
 * October with the playhead's day nowhere on screen.
 *
 * Each day square shows Net, Gross, Commissions or Trades; hovering a day opens
 * its breakdown card and clicking it opens the day (operator ask, 2026-10-26).
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { dayBreakdowns } from './accountDayBreakdown';
import { paperHistoryFixture } from './accountFixtures';
import { CalendarPanel } from './CalendarPanel';

afterEach(cleanup);

// The replay playhead: Fri 2026-09-18 10:00 ET; the fixture's today row is that day.
const PLAYHEAD = Date.parse('2026-09-18T10:00:00-04:00') / 1000;
const history = paperHistoryFixture(PLAYHEAD);
const days = dayBreakdowns(history);

const title = () => screen.getByTestId('account-calendar-title').textContent;
const panel = (today: string, props: { selected?: string | null; onSelect?: (d: string | null) => void } = {}) => (
  <CalendarPanel history={history} absence={null} today={today} days={days} selected={props.selected ?? null} onSelect={props.onSelect ?? (() => {})} />
);
const cell = (date: string) => screen.getByTestId(`account-calendar-day-${date}`);

describe('CalendarPanel month', () => {
  it("opens on today's month and follows today into another month", () => {
    // First render on Sim: the browser's day, before the Sim clock answers.
    const { rerender } = render(panel('2026-10-01'));
    expect(title()).toBe('October 2026');

    rerender(panel('2026-09-18'));
    expect(title()).toBe('September 2026');
    expect(cell('2026-09-18').className).toMatch(/is-today/);
    expect(screen.queryByTestId('account-calendar-day-2026-10-01')).toBeNull();
  });

  it("keeps a month browsed to until today's month moves", () => {
    const { rerender } = render(panel('2026-09-18'));
    fireEvent.click(screen.getByTestId('account-calendar-prev'));
    expect(title()).toBe('August 2026');

    // Today moves within its month (a scrub, the 04:00 ET rollover): the browse stays.
    rerender(panel('2026-09-21'));
    expect(title()).toBe('August 2026');
    fireEvent.click(screen.getByTestId('account-calendar-next'));
    expect(title()).toBe('September 2026');
    expect(cell('2026-09-21').className).toMatch(/is-today/);

    // Today moves to another month (a replay of another day, a venue switch): the calendar follows.
    fireEvent.click(screen.getByTestId('account-calendar-prev'));
    rerender(panel('2026-10-02'));
    expect(title()).toBe('October 2026');
    expect(cell('2026-10-02').className).toMatch(/is-today/);
  });
});

describe('CalendarPanel day squares', () => {
  it('shows the net and the trade count, and switches to gross, commissions and trades', () => {
    render(panel('2026-09-18'));
    expect(cell('2026-09-18').textContent).toBe('18+$87.102 trades');
    // A day only an archived ledger traded counts its fills: its trades are not sent.
    expect(cell('2026-09-10').textContent).toBe('10+$96.352 fills');

    fireEvent.click(screen.getByTestId('account-calendar-metric-gross'));
    expect(cell('2026-09-18').textContent).toBe('18+$97.502 trades');
    expect(screen.getByTestId('account-calendar-foot').textContent).toBe(
      'Gross +$196.05 before -$12.00 commissions and -$0.60 fees · blank = no fills',
    );

    fireEvent.click(screen.getByTestId('account-calendar-metric-commissions'));
    expect(screen.getByTestId('account-calendar-metric-commissions').getAttribute('aria-pressed')).toBe('true');
    expect(cell('2026-09-18').textContent).toBe('18-$10.002 trades');
    // Per trade only when every day's trades are known.
    expect(screen.getByTestId('account-calendar-foot').textContent).toBe('Commissions -$12.00 · fees -$0.60 · blank = no fills');

    fireEvent.click(screen.getByTestId('account-calendar-metric-trades'));
    expect(cell('2026-09-18').textContent).toBe('1826 fills');
    expect(cell('2026-09-10').textContent).toBe('10—2 fills');
    expect(screen.getByTestId('account-calendar-foot').textContent).toBe(
      "2 trades · 8 fills · 1 won, 1 lost · archived ledgers' trades are not counted · blank = no fills",
    );

    fireEvent.click(screen.getByTestId('account-calendar-metric-net'));
    expect(screen.getByTestId('account-calendar-foot').textContent).toContain('this ledger');
  });

  it('gives commissions per trade only when every trade of the month is counted (a reset mid-day hides it)', () => {
    const current = paperHistoryFixture(PLAYHEAD);
    current.daily = current.daily.filter((r) => !r.archived);
    const foot = () => screen.getByTestId('account-calendar-foot').textContent;
    const show = (h: typeof current) => (
      <CalendarPanel history={h} absence={null} today="2026-09-18" days={dayBreakdowns(h)} selected={null} onSelect={() => {}} />
    );
    const { rerender } = render(show(current));
    fireEvent.click(screen.getByTestId('account-calendar-metric-commissions'));
    expect(foot()).toBe('Commissions -$10.00 · fees -$0.40 · $5.00 a trade · blank = no fills');

    // Paper reset at noon: the archived ledger's $100 is in the day, its trades are not.
    const reset = { ...current, daily: [...current.daily, { date: '2026-09-18', realized: -100, commissions: 100, fees: 0, fills: 2, archived: true }] };
    rerender(show(reset));
    expect(foot()).toBe('Commissions -$110.00 · fees -$0.40 · blank = no fills');
  });

  it('opens the hover card on a day and closes it when the pointer leaves', () => {
    render(panel('2026-09-18'));
    fireEvent.mouseEnter(cell('2026-09-18'));
    const card = screen.getByTestId('account-calendar-card');
    expect(card.textContent).toContain('Friday, Sep 18');
    expect(card.textContent).toContain('Gross+$97.50');
    expect(card.textContent).toContain('Commissions-$10.00');
    expect(card.textContent).toContain('SEC + FINRA fees-$0.40');
    expect(card.textContent).toContain('Trades2 · 1 won · 1 lost');
    expect(card.textContent).toContain('Fills6 · 2 by the bot');
    expect(card.textContent).toContain('Shares1,150 bought · 750 sold');
    expect(card.textContent).toContain('Stocks2 · GRML, QNME');
    fireEvent.mouseLeave(cell('2026-09-18'));
    expect(screen.queryByTestId('account-calendar-card')).toBeNull();

    // An archived ledger's day: its totals and why nothing more is listed.
    fireEvent.mouseEnter(cell('2026-09-10'));
    const archived = within(screen.getByTestId('account-calendar-card'));
    expect(archived.getByText(/keeps only its day totals/)).toBeTruthy();
    expect(archived.queryByText('Trades')).toBeNull();
  });

  it('opens a day on click and closes it on a second click; a weekend is not a button', () => {
    const onSelect = vi.fn();
    const { rerender } = render(panel('2026-09-18', { onSelect }));
    fireEvent.click(cell('2026-09-18'));
    expect(onSelect).toHaveBeenLastCalledWith('2026-09-18');

    rerender(panel('2026-09-18', { onSelect, selected: '2026-09-18' }));
    expect(cell('2026-09-18').className).toMatch(/is-sel/);
    expect(cell('2026-09-18').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(cell('2026-09-18'));
    expect(onSelect).toHaveBeenLastCalledWith(null);

    expect(cell('2026-09-19').tagName).toBe('DIV');
    expect(cell('2026-09-19').getAttribute('title')).toBe('no session');
  });
});
