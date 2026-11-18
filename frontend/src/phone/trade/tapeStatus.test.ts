/**
 * The phone's tape always says whether it is live (operator report 2026-11-17: "the time and sale was not moving
 * ... there was a missing piece"). A quiet stock, a dead line, a quiet socket and a screen still connecting used to
 * look the same.
 */
import { describe, expect, it } from 'vitest';
import { emptyTapeState, type TapePrint, type TapeState } from '../../ibkr/tapeFeed';
import { tapeStatus } from './TapeStatus';

const NOW = Date.parse('2026-11-17T19:35:24.000Z');   // 14:35:24 ET: GMM had printed nothing for 23 s

function printAt(iso: string): TapePrint {
  return { symbol: 'GMM', time: iso, price: 1.3, size: 200, exchange: 'FINRA' };
}

function tape(over: Partial<TapeState>): TapeState {
  return { ...emptyTapeState(), connected: true, ...over };
}

describe('tapeStatus', () => {
  it('reads LIVE, and says how old the newest print is once it is 5 s old', () => {
    expect(tapeStatus(tape({ prints: [printAt('2026-11-17T19:35:22.000Z')] }), NOW))
      .toEqual({ label: 'LIVE', tone: 'good', age: null, note: null, live: true });
    expect(tapeStatus(tape({ prints: [printAt('2026-11-17T19:35:01.502Z')] }), NOW))
      .toMatchObject({ label: 'LIVE', age: 'last 22s', live: true });
    expect(tapeStatus(tape({ prints: [] }), NOW)).toMatchObject({ label: 'LIVE', age: null, live: true });
  });

  it("uses the desk's own word and count for a line with no print, and fades the rows only when it may be down", () => {
    const since = NOW / 1000 - 45;
    expect(tapeStatus(tape({ silence: { state: 'quiet', since, text: 'Nothing traded.' } }), NOW))
      .toMatchObject({ label: 'QUIET 45s', tone: 'quiet', note: null, live: true });
    expect(tapeStatus(tape({ silence: { state: 'halted', since, text: 'Halted.' } }), NOW))
      .toMatchObject({ label: 'HALTED', tone: 'warn', live: true });
    const dead = tapeStatus(tape({ silence: { state: 'dead', since, text: 'Level 1 counted trades.' } }), NOW);
    expect(dead).toMatchObject({ label: 'LINE DOWN 45s', tone: 'bad', live: false });
    expect(dead.note).toMatch(/IBKR's tape line is down$/);
    expect(tapeStatus(tape({ silence: { state: 'silent', since, text: 'Level 2 moves.' } }), NOW))
      .toMatchObject({ label: 'SILENT 45s', tone: 'warn', live: false });
  });

  it('says NO DATA while the socket to the PC has said nothing, whatever the last frame claimed', () => {
    const status = tapeStatus(tape({ connected: false, quietSince: NOW - 6_400, prints: [printAt('2026-11-17T19:35:17.000Z')] }), NOW);
    expect(status).toEqual({
      label: 'NO DATA 6s', tone: 'bad', age: null, note: 'No word from your PC on this tape. Asking again.', live: false,
    });
  });

  it('says where your lane is, an error in the desk\'s words, a retry, and a screen still connecting', () => {
    const lane = { you: 'SLS', text: 'click', plain: 'Your Time & Sales is on SLS' };
    expect(tapeStatus(tape({ connected: false, laneWait: lane }), NOW))
      .toMatchObject({ label: 'NO LANE', note: 'Your Time & Sales is on SLS', live: false });
    expect(tapeStatus(tape({ connected: false, error: 'IBKR not connected' }), NOW))
      .toMatchObject({ label: 'ERROR', tone: 'bad', note: 'IBKR not connected', live: false });
    expect(tapeStatus(tape({ connected: false, error: 'Resubscribing in 10s', retryAt: NOW / 1000 + 10 }), NOW))
      .toMatchObject({ label: 'RETRYING', tone: 'warn', live: false });
    expect(tapeStatus(tape({ connected: false }), NOW))
      .toMatchObject({ label: 'CONNECTING', tone: 'quiet', note: null, live: false });
  });
});
