/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { stageSetupTicket } from './stageSetupTicket';
import * as prefill from '../ibkr/orderTicketPrefill';
import { SETUPS_STAGE_TICKET_DELAY_MS } from '../constants';

const desk = vi.hoisted(() => ({ current: { venue: 'paper' as 'paper' | 'live' | null, generation: 'paper-1' as string | null } }));
vi.mock('../ibkr', () => ({
  getConfirmedDeskVenueSnapshot: () => desk.current,
  isConfirmedDeskVenueSnapshotCurrent: (asked: typeof desk.current) => asked.venue === desk.current.venue && asked.generation === desk.current.generation,
  defaultTicketQty: (venue: string) => venue === 'paper' ? '7' : '31',
}));

describe('setup ticket staging follows its confirmed venue generation', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    desk.current = { venue: 'paper', generation: 'paper-1' };
  });
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.restoreAllMocks(); });

  it('stages immediately and retries on the same confirmed venue for a mounting ticket', () => {
    const send = vi.spyOn(prefill, 'requestOrderTicketPrefill');
    expect(stageSetupTicket('AAPL', '10.00', vi.fn())).toBe(true);
    expect(send.mock.calls[0][0].quantityValue).toBe('7');
    vi.advanceTimersByTime(SETUPS_STAGE_TICKET_DELAY_MS);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it.each(['live', 'paper'] as const)('drops a delayed Paper stage after a transition ending on %s', (endVenue) => {
    const send = vi.spyOn(prefill, 'requestOrderTicketPrefill');
    stageSetupTicket('AAPL', '10.00', vi.fn());
    desk.current = { venue: endVenue, generation: endVenue === 'paper' ? 'paper-after-live' : 'live-1' };
    vi.advanceTimersByTime(SETUPS_STAGE_TICKET_DELAY_MS);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('refuses to stage while the desk venue is unknown', () => {
    desk.current = { venue: null, generation: null };
    const send = vi.spyOn(prefill, 'requestOrderTicketPrefill');
    const openTrader = vi.fn();
    expect(stageSetupTicket('AAPL', '10.00', openTrader)).toBe(false);
    expect(openTrader).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(send).not.toHaveBeenCalled();
  });
});
