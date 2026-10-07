/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { proposalRisk, proposalStageSize } from './proposalVerdict';
import { shortStageOf, stageSetupTicket } from './stageSetupTicket';
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

  it('stages a short setup\'s proposal as a short with its buy stop, never a buy (ADR 049)', () => {
    const send = vi.spyOn(prefill, 'requestOrderTicketPrefill');
    const short = shortStageOf({ side: 'short', setup_type: 'bear_flag', stop: 5.53 });
    expect(short).toEqual({ buyStop: '5.53' });
    expect(stageSetupTicket('FADE', '5.39', vi.fn(), 142, short)).toBe(true);
    expect(send.mock.calls[0][0]).toEqual({ symbol: 'FADE', side: 'SELL', orderType: 'LMT', quantityValue: '142',
      limitPrice: '5.39', shortEntry: true, buyStop: '5.53' });
    expect(shortStageOf({ side: 'long', setup_type: 'first_pullback', stop: 4.62 })).toBeNull();
  });

  it('stages nothing for a short with no stop: no stop, no short', () => {
    const send = vi.spyOn(prefill, 'requestOrderTicketPrefill');
    const openTrader = vi.fn();
    const short = shortStageOf({ setup_type: 'bear_flag', stop: null });
    expect(short).toEqual({ buyStop: '' });
    expect(stageSetupTicket('FADE', '5.39', openTrader, 142, short)).toBe(false);
    expect(openTrader).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
    expect(proposalStageSize({ risk: 0.14, entry: 5.39, stop: null, side: 'short' }, 20, 'the Paper sleeve\'s').qty)
      .toBeNull();
  });

  it('sizes a short by its buy stop over the entry', () => {
    expect(proposalRisk({ risk: null, entry: 5.39, stop: 5.53, side: 'short' })).toBeCloseTo(0.14);
    expect(proposalRisk({ risk: null, entry: 5.39, stop: 5.53 })).toBeNull();          // a long's stop is under it
    expect(proposalStageSize({ risk: null, entry: 5.39, stop: 5.53, side: 'short' }, 20, 'the Paper sleeve\'s').qty).toBe(142);
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
