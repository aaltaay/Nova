/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CloseReminders } from './CloseReminders';
import { resetCloseRemindersForTests } from './closeReminderStore';

// 2026-10-02 (Friday) 15:50:30 ET = 19:50:30Z (EDT).
const AT_1550 = new Date('2026-10-02T19:50:30Z');
const AT_1555 = new Date('2026-10-02T19:55:10Z');

describe('CloseReminders', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(AT_1550);
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    resetCloseRemindersForTests();
  });

  it('shows a loud card for an open Paper position at 15:50, opens the symbol, dismisses once per stage, escalates at 15:55', () => {
    const open = vi.fn();
    const { rerender } = render(<CloseReminders positions={[{ symbol: 'GRML', qty: 500 }]} venue="paper" onOpenSymbol={open} />);
    const card = screen.getByTestId('close-reminder');
    expect(card.getAttribute('role')).toBe('alert');
    expect(card.getAttribute('data-stage')).toBe('warn');
    expect(screen.getByTestId('close-reminder-title').textContent).toBe('Still holding 500 GRML at 15:50 -- be flat by 15:55');
    expect(card.textContent).toContain('Paper position');

    fireEvent.click(screen.getByTestId('close-reminder-open'));
    expect(open).toHaveBeenCalledWith('GRML');
    expect(screen.getByTestId('close-reminder')).toBeTruthy(); // Open keeps the card: the position is still open

    fireEvent.click(screen.getByTestId('close-reminder-dismiss'));
    expect(screen.queryByTestId('close-reminder')).toBeNull();
    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(screen.queryByTestId('close-reminder')).toBeNull(); // not again at the same stage

    vi.setSystemTime(AT_1555);
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    const final = screen.getByTestId('close-reminder');
    expect(final.getAttribute('data-stage')).toBe('final');
    expect(screen.getByTestId('close-reminder-title').textContent).toBe('15:55: 500 GRML still open -- close it now');

    rerender(<CloseReminders positions={[]} venue="paper" onOpenSymbol={open} />);
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(screen.queryByTestId('close-reminder')).toBeNull(); // flat: the card leaves
  });

  it('shows nothing on Sim or before 15:50', () => {
    render(<CloseReminders positions={[{ symbol: 'GRML', qty: 500 }]} venue="sim" />);
    expect(screen.queryByTestId('close-reminder')).toBeNull();
    cleanup();
    vi.setSystemTime(new Date('2026-10-02T19:40:00Z'));
    render(<CloseReminders positions={[{ symbol: 'GRML', qty: 500 }]} venue="live" />);
    expect(screen.queryByTestId('close-reminder')).toBeNull();
  });

  it('says the rows are last known when the Gateway dropped', () => {
    render(<CloseReminders positions={[{ symbol: 'ACN', qty: -100 }]} venue="live" stale />);
    expect(screen.getByTestId('close-reminder-title').textContent).toBe('Still holding 100 short ACN at 15:50 -- be flat by 15:55');
    expect(screen.getByTestId('close-reminder').textContent).toContain('last known: the Gateway dropped');
  });
});
