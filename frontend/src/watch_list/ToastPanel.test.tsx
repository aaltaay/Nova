/**
 * @vitest-environment jsdom
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastPanel } from './ToastPanel';
import { resetToastScoresForTests } from './toastScores';
import { getToastWindow, resetToastWindowForTests } from './toastWindow';
import { WATCH_TOAST_SCORES_EMPTY, WATCH_TOAST_SCORES_KEY } from './watchListConstants';

/** 2026-09-23 10:30 ET. */
const NOW = Date.UTC(2026, 8, 23, 14, 30);

function reset(): void {
  cleanup();
  vi.useRealTimers();
  localStorage.clear();
  resetToastScoresForTests();
  resetToastWindowForTests();
}

describe('the Hot list tab toast panel', () => {
  beforeEach(() => {
    reset();
    vi.useFakeTimers({ now: NOW, toFake: ['Date'] });
  });
  afterEach(reset);

  it('sets the window toasts come in, refusing one that ends before it starts', () => {
    render(<ToastPanel />);
    expect((screen.getByTestId('watch-toast-window-start') as HTMLInputElement).value).toBe('07:00');
    fireEvent.change(screen.getByTestId('watch-toast-window-end'), { target: { value: '10:00' } });
    expect(getToastWindow()).toEqual({ start: '07:00', end: '10:00' });
    fireEvent.change(screen.getByTestId('watch-toast-window-start'), { target: { value: '11:00' } });
    expect(screen.getByRole('alert').textContent).toBe('The end must be after the start');
    expect(getToastWindow()).toEqual({ start: '07:00', end: '10:00' });
    fireEvent.click(screen.getByTestId('watch-toast-window-reset'));
    expect(getToastWindow()).toEqual({ start: '07:00', end: '16:00' });
  });

  it("shows today's toasts by kind and what was held back", () => {
    render(<ToastPanel />);
    expect(screen.getByTestId('watch-toast-scores').textContent).toContain(WATCH_TOAST_SCORES_EMPTY);
    cleanup();
    localStorage.setItem(WATCH_TOAST_SCORES_KEY, JSON.stringify({
      schema_version: 1, day: '2026-09-23',
      toasts: [
        { id: 'a', symbol: 'GRML', kind: 'armed', at: NOW - 600_000, price: 4, score: { ref: 4, after: 4.2, move: 0.05 } },
        { id: 'b', symbol: 'ONCO', kind: 'armed', at: NOW - 500_000, price: 4, score: { ref: 4, after: 3.8, move: -0.05 } },
        { id: 'c', symbol: 'MEDS', kind: 'armed', at: NOW - 60_000, price: 4, score: null },
      ],
      held: { running_up: 912, quiet: 3 },
    }));
    resetToastScoresForTests();
    render(<ToastPanel />);
    const armed = screen.getByTestId('watch-toast-score-armed');
    expect([...armed.querySelectorAll('td')].map(td => td.textContent))
      .toEqual(['Setup armed', '3', '2', '1 of 2', '0.00%']);
    expect(screen.getByTestId('watch-toast-held').textContent).toBe('Held back: 912 Running Up · 3 quiet after a toast');
  });
});
