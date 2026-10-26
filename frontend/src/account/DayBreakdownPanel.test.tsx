/**
 * @vitest-environment jsdom
 *
 * One Calendar day opened: where the money went (gross, less commissions,
 * less fees, equals net), the day's tiles, every stock and every trade.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { dayBreakdowns, type DayBreakdown } from './accountDayBreakdown';
import { paperHistoryFixture } from './accountFixtures';
import { DayBreakdownPanel, waterfallSteps } from './DayBreakdownPanel';

afterEach(cleanup);

const PLAYHEAD = Date.parse('2026-09-18T10:00:00-04:00') / 1000;
const days = dayBreakdowns(paperHistoryFixture(PLAYHEAD));
const day = days.get('2026-09-18')!;

describe('waterfallSteps', () => {
  it('runs gross down through commissions and fees to net', () => {
    const steps = waterfallSteps({ gross: -20.38, commissions: 44.71, fees: 1.28, net: -66.37 });
    expect(steps.map((s) => [s.key, s.from, s.to])).toEqual([
      ['gross', 0, -20.38],
      ['commissions', -20.38, -20.38 - 44.71],
      ['fees', -20.38 - 44.71, -66.37],
      ['net', 0, -66.37],
    ]);
  });
});

describe('DayBreakdownPanel', () => {
  it('shows the day, where its money went, its tiles, stocks and trades', () => {
    render(<DayBreakdownPanel day={day} onClose={() => {}} onShowFills={() => {}} />);
    expect(screen.getByTestId('account-day-date').textContent).toBe('Friday, Sep 18');
    expect(screen.getByTestId('account-day-net').textContent).toBe('+$87.10');
    expect(screen.getByTestId('account-day-step-gross').textContent).toContain('+$97.50');
    expect(screen.getByTestId('account-day-step-commissions').textContent).toContain('-$10.00');
    expect(screen.getByTestId('account-day-step-fees').textContent).toContain('-$0.40');
    expect(screen.getByTestId('account-day-step-net').textContent).toContain('+$87.10');
    expect(screen.getByTestId('account-day-stock-GRML').textContent).toContain('6.73 → 5.35');
    expect(screen.getByTestId('account-day-stock-QNME').textContent).toContain('-$30.20');
    expect(screen.getAllByTestId('account-day-trade').map((r) => r.textContent)).toEqual([
      expect.stringContaining('GRMLLong500Manual'),
      expect.stringContaining('QNMELong250Bot'),
    ]);
    expect(screen.getByTestId('account-day-show-fills').textContent).toBe('Show these 6 fills ↓');
  });

  it('closes, and asks for the fills', () => {
    const onClose = vi.fn();
    const onShowFills = vi.fn();
    render(<DayBreakdownPanel day={day} onClose={onClose} onShowFills={onShowFills} />);
    fireEvent.click(screen.getByTestId('account-day-show-fills'));
    expect(onShowFills).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('account-day-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('lists eight trades, then all of them on request', () => {
    const trade = day.trades[0];
    const busy: DayBreakdown = {
      ...day,
      trades: Array.from({ length: 11 }, (_, i) => ({ ...trade, openTs: trade.openTs + i * 60, closeTs: trade.closeTs + i * 60 })),
    };
    render(<DayBreakdownPanel day={busy} onClose={() => {}} onShowFills={() => {}} />);
    expect(screen.getAllByTestId('account-day-trade')).toHaveLength(8);
    fireEvent.click(screen.getByTestId('account-day-more'));
    expect(screen.getAllByTestId('account-day-trade')).toHaveLength(11);
    expect(screen.getByTestId('account-day-more').textContent).toBe('Show fewer');
  });

  it('gives commissions per trade on a whole day, and none when an archived ledger shared the day', () => {
    const { rerender } = render(<DayBreakdownPanel day={day} onClose={() => {}} onShowFills={() => {}} />);
    expect(screen.getByText('$5.00 a trade')).toBeTruthy();
    rerender(<DayBreakdownPanel day={{ ...day, commissions: 110, partial: true }} onClose={() => {}} onShowFills={() => {}} />);
    expect(screen.queryByText(/a trade$/)).toBeNull();
    expect(screen.getByText('no per-trade figure · archived share')).toBeTruthy();
    expect(screen.getByText(/Part of this day belongs to an archived ledger/)).toBeTruthy();
  });

  it("states an archived ledger's day as its totals, with nothing to list", () => {
    render(<DayBreakdownPanel day={days.get('2026-09-10')!} onClose={() => {}} onShowFills={() => {}} />);
    expect(screen.getByText(/keeps only its day totals/)).toBeTruthy();
    expect(screen.getByTestId('account-day-step-gross').textContent).toContain('+$98.55');
    expect(screen.queryByTestId('account-day-stocks')).toBeNull();
    expect(screen.queryByTestId('account-day-show-fills')).toBeNull();
  });
});
