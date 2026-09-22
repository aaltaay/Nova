import { describe, expect, it } from 'vitest';
import { SIM_REPLAY_PRICE_NONE, SIM_REPLAY_PRICE_NOT_RECORDED } from './simConstants';
import type { SimClockState } from './simClockTypes';
import { replayQuoteFor } from './useReplayQuote';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

const capture = (quote: SimClockState['replay_quote']): SimClockState => ({
  sim: true, live_edge: false, replay_source: 'capture', replay_symbol: 'GRML', replay_quote: quote,
});
const QUOTE = { symbol: 'GRML', ts: 1, covered: true, last: 8.84, bid: 8.82, ask: 8.85, bid_size: 100, ask_size: 200, prev_close: 8.0 };

describe('replayQuoteFor (R10 / V24)', () => {
  it('off Sim, or at the live edge, the live feed is the price', () => {
    expect(replayQuoteFor('GRML', capture(QUOTE), null, false).active).toBe(false);
    expect(replayQuoteFor('GRML', { ...capture(QUOTE), live_edge: true }, null, true).active).toBe(false);
  });

  it("a capture replay of this tab is priced from the clock's quote at the playhead", () => {
    expect(replayQuoteFor('grml', capture(QUOTE), null, true)).toEqual({
      active: true, last: 8.84, bid: 8.82, ask: 8.85, prevClose: 8.0, note: null,
    });
  });

  it('a gap in the recording has no price and says why', () => {
    const gap = replayQuoteFor('GRML', capture({ ...QUOTE, covered: false, last: null, bid: null, ask: null }), null, true);
    expect(gap).toMatchObject({ active: true, last: null, note: SIM_REPLAY_PRICE_NOT_RECORDED });
  });

  it('a historical replay of this tab is priced from its snapshot', () => {
    const clock: SimClockState = { sim: true, live_edge: false, replay_source: 'historical', replay_symbol: 'IMCC' };
    const snap = { active: true, symbol: 'IMCC', last: 5.1, volume: 10, source: 'trades', as_of: '', prints: [],
      prev_close: 4.9, covered: true } as HistoricalSnapshot;
    expect(replayQuoteFor('IMCC', clock, snap, true)).toMatchObject({ active: true, last: 5.1, prevClose: 4.9, note: null });
    expect(replayQuoteFor('IMCC', clock, { ...snap, covered: false }, true).note).toBe(SIM_REPLAY_PRICE_NOT_RECORDED);
  });

  it('nothing loaded, another symbol loaded, or no clock yet: no price -- never the live last', () => {
    const none = { sim: true, live_edge: false, replay_source: 'none' } as SimClockState;
    expect(replayQuoteFor('GRML', none, null, true)).toMatchObject({ active: true, last: null, note: SIM_REPLAY_PRICE_NONE });
    expect(replayQuoteFor('SPY', capture(QUOTE), null, true).last).toBeNull();
    expect(replayQuoteFor('GRML', null, null, true)).toMatchObject({ active: true, last: null });
  });
});
