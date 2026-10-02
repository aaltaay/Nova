/**
 * @vitest-environment jsdom
 *
 * The calendar shows today's month and moves with it. `today` changes under a
 * mounted panel: on Sim the page reads the browser's clock until the Sim clock
 * answers, then the replay playhead's day (C20 / V32). The panel used to keep
 * the month of its first render, so from 2026-10-01 a replayed Sep 18 opened on
 * October with the playhead's day nowhere on screen.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { paperHistoryFixture } from './accountFixtures';
import { CalendarPanel } from './CalendarPanel';

afterEach(cleanup);

// The replay playhead: Fri 2026-09-18 10:00 ET; the fixture's today row is that day.
const PLAYHEAD = Date.parse('2026-09-18T10:00:00-04:00') / 1000;
const history = paperHistoryFixture(PLAYHEAD);

const title = () => screen.getByTestId('account-calendar-title').textContent;

describe('CalendarPanel month', () => {
  it("opens on today's month and follows today into another month", () => {
    // First render on Sim: the browser's day, before the Sim clock answers.
    const { rerender } = render(<CalendarPanel history={history} absence={null} today="2026-10-01" />);
    expect(title()).toBe('October 2026');

    rerender(<CalendarPanel history={history} absence={null} today="2026-09-18" />);
    expect(title()).toBe('September 2026');
    expect(screen.getByTestId('account-calendar-day-2026-09-18').className).toMatch(/is-today/);
    expect(screen.queryByTestId('account-calendar-day-2026-10-01')).toBeNull();
  });

  it("keeps a month browsed to until today's month moves", () => {
    const { rerender } = render(<CalendarPanel history={history} absence={null} today="2026-09-18" />);
    fireEvent.click(screen.getByTestId('account-calendar-prev'));
    expect(title()).toBe('August 2026');

    // Today moves within its month (a scrub, the 04:00 ET rollover): the browse stays.
    rerender(<CalendarPanel history={history} absence={null} today="2026-09-21" />);
    expect(title()).toBe('August 2026');
    fireEvent.click(screen.getByTestId('account-calendar-next'));
    expect(title()).toBe('September 2026');
    expect(screen.getByTestId('account-calendar-day-2026-09-21').className).toMatch(/is-today/);

    // Today moves to another month (a replay of another day, a venue switch): the calendar follows.
    fireEvent.click(screen.getByTestId('account-calendar-prev'));
    rerender(<CalendarPanel history={history} absence={null} today="2026-10-02" />);
    expect(title()).toBe('October 2026');
    expect(screen.getByTestId('account-calendar-day-2026-10-02').className).toMatch(/is-today/);
  });
});
