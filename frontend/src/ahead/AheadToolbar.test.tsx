/**
 * @vitest-environment jsdom
 *
 * The Ahead switch (ADR 061): off by default, kept in prefs, a "new" badge, and words when no 1-minute pane draws it.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { publishAheadScene } from './AheadChartLayer';
import { AHEAD_WORDS } from './aheadConstants';
import { readAheadPrefs, reloadAheadPrefsForTesting } from './aheadPrefs';
import { sampleScene } from './aheadTestKit';
import { AheadToolbar } from './AheadToolbar';

vi.mock('../stock_read', async (orig) => ({
  ...(await orig<typeof import('../stock_read')>()),
  useStockReadContext: () => ({ symbol: 'XYZ' }),
}));

beforeEach(() => {
  localStorage.clear();
  reloadAheadPrefsForTesting();
});

afterEach(() => {
  cleanup();
  act(() => publishAheadScene('XYZ', null));
});

describe('AheadToolbar', () => {
  it('is off by default and switches Ahead on and off', () => {
    render(<AheadToolbar />);
    const button = screen.getByTestId('ahead-toggle');
    expect(button.getAttribute('aria-pressed')).toBe('false');
    expect(button.textContent).toContain(AHEAD_WORDS.newBadge);
    expect(button.getAttribute('title')).toBe(AHEAD_WORDS.toggleTitle);
    fireEvent.click(button);
    expect(readAheadPrefs().shown).toBe(true);
    expect(screen.getByTestId('ahead-toggle').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('ahead-toggle'));
    expect(readAheadPrefs().shown).toBe(false);
  });

  it('says Ahead draws on the 1-minute chart while on with no 1-minute pane', () => {
    render(<AheadToolbar />);
    fireEvent.click(screen.getByTestId('ahead-toggle'));
    expect(screen.getByTestId('ahead-no-pane').textContent).toBe(AHEAD_WORDS.onlyOneMinute);
    act(() => publishAheadScene('XYZ', sampleScene()));
    expect(screen.queryByTestId('ahead-no-pane')).toBeNull();
  });
});
