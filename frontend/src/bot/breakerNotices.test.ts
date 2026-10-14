import { afterEach, describe, expect, it } from 'vitest';
import {
  BREAKER_NOTICE_MAX_AGE_SEC,
  breakerTripBody,
  breakerTripOf,
  breakerTripTitle,
  noteBreakerTrips,
  resetBreakerTripsForTests,
  takeNewBreakerTrips,
} from './breakerNotices';
import type { BotAuditEntry } from './types';

// 2026-10-01 09:43:05.927 ET -- the Paper bot trip that sold 100 ACN.
const AT = 1790862185.927;

function line(over: Partial<BotAuditEntry> = {}): BotAuditEntry {
  return {
    timestamp: AT,
    level: 0,
    brain_session_id: null,
    action: 'breaker_soft',
    inputs: {
      flatten_ok: true,
      threshold: -50,
      pnl: -66.07,
      venue: 'paper',
      until: '2026-10-02T04:00:00-04:00',
      closes: [{ symbol: 'ACN', side: 'SELL', qty: 100, ok: true, order_id: 68, error: null }],
      flatten_error: null,
    },
    reason: 'paper: the day P&L -66.07 reached the bot trip (-50) -- flattened, the bot is Off ...',
    order_id: null,
    outcome: 'l0',
    venue: 'paper',
    ...over,
  };
}

afterEach(() => resetBreakerTripsForTests());

describe('the loss breakers\' notice', () => {
  it('says what tripped, what it sold and what follows', () => {
    const trip = breakerTripOf(line())!;
    expect(breakerTripTitle(trip)).toBe('Bot trip sold your positions');
    const body = breakerTripBody(trip).split('\n');
    expect(body[0]).toBe('Paper · day P&L -$66.07 reached your -$50.00 limit · 09:43:05 ET');
    expect(body[1]).toBe('Sold 100 ACN · order 68');
    expect(body[2]).toMatch(/bot is Off until 04:00 ET/);
  });

  it('says the all-stop locked buys, and a failed sell loudly', () => {
    const hard = breakerTripOf(line({ action: 'breaker_hard', inputs: { ...line().inputs, threshold: -200, pnl: -210 } }))!;
    expect(breakerTripTitle(hard)).toBe('All-stop sold your positions');
    expect(breakerTripBody(hard)).toMatch(/Buys on Paper are locked until 04:00 ET/);
    const failed = breakerTripOf(line({
      inputs: {
        ...line().inputs,
        flatten_ok: false,
        flatten_error: 'positions still open after flatten: ACN 100',
        closes: [{ symbol: 'ACN', side: 'SELL', qty: 100, ok: false, order_id: null, error: 'no mark' }],
      },
    }))!;
    expect(breakerTripTitle(failed)).toMatch(/the sell failed — close your positions yourself/);
    expect(breakerTripBody(failed)).toMatch(/100 ACN was not sold — no mark/);
    expect(breakerTripBody(failed)).toMatch(/positions still open after flatten/);
  });

  it('never invents what an older backend did not say', () => {
    const { closes: _closes, ...inputs } = line().inputs as Record<string, unknown>;
    const trip = breakerTripOf(line({ inputs }))!;
    expect(trip.closes).toBeNull();
    expect(breakerTripBody(trip)).toMatch(/The Orders table lists them/);
    const empty = breakerTripOf(line({ inputs: { ...line().inputs, closes: [] } }))!;
    expect(breakerTripBody(empty)).toMatch(/Nothing was held/);
  });

  it('ignores every other audit line', () => {
    expect(breakerTripOf(line({ action: 'breaker_soft_flatten' }))).toBeNull();
    expect(breakerTripOf(line({ action: 'deactivate' }))).toBeNull();
  });

  it('announces each trip once, and only while it is recent', () => {
    const seen = new Set<string>();
    const old = line({ timestamp: AT - BREAKER_NOTICE_MAX_AGE_SEC - 1 });
    expect(takeNewBreakerTrips([old, line()], seen, AT + 5).map((t) => t.at)).toEqual([AT]);
    expect(takeNewBreakerTrips([old, line()], seen, AT + 7)).toEqual([]);
  });

  it('raises a notice that stays until dismissed, once per trip', () => {
    const pushed: { tone: string; title: string }[] = [];
    const push = (n: { tone: string; title: string; text: string }) => pushed.push(n);
    expect(noteBreakerTrips([], push, AT + 5)).toBe(0);
    expect(noteBreakerTrips([line()], push, AT + 5)).toBe(1);
    expect(noteBreakerTrips([line()], push, AT + 7)).toBe(0);
    expect(pushed).toEqual([expect.objectContaining({ tone: 'bad', title: 'Bot trip sold your positions' })]);
  });
});

// 2026-10-14 09:28:27 ET: the Paper bot trip sold 1,000 GENK that a 3-minute-old buy had bought 0.8 s earlier,
// and the operator was sure there had been no order.
describe('the trip names the order behind what it sold', () => {
  const GENK_TRIP = 1791984507.42;

  it('says which order opened the position, when it was placed and when it filled', () => {
    const trip = breakerTripOf(line({
      timestamp: GENK_TRIP,
      inputs: {
        flatten_ok: true, threshold: -405, pnl: -425.34, venue: 'paper', flatten_error: null,
        closes: [{
          symbol: 'GENK', side: 'SELL', qty: 1000, ok: true, order_id: 256, error: null,
          opened_by: {
            order_id: 255, source: 'manual', side: 'BUY', qty: 1000, order_type: 'LMT', price: 2.76,
            placed_ts: 1791984319.81, filled_ts: 1791984506.6,
          },
        }],
      },
    }))!;
    const body = breakerTripBody(trip).split('\n');
    expect(body[1]).toBe('Sold 1,000 GENK · order 256');
    expect(body[2]).toBe(
      'It came from your order 255: Buy 1,000 GENK LMT 2.76, placed 09:25:19 ET, filled 09:28:26 ET.',
    );
  });

  it('says nothing more when the backend could not tell, or the close failed', () => {
    const trip = breakerTripOf(line())!;
    expect(breakerTripBody(trip).split('\n')[2]).toMatch(/^The bot is Off/);
  });
});
