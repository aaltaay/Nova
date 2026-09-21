import { describe, expect, it } from 'vitest';
import { simRailNote, simReplayTarget } from './simReplayTarget';
import { simEmptyQuoteDetail } from './historicalQuoteDetail';
import type { TickerDetail } from '../types/ticker';
import type { SimClockState } from './simClockTypes';

const clock = (over: Partial<SimClockState> = {}): SimClockState => ({ sim: true, ...over });

describe('simReplayTarget', () => {
  it('says nothing outside Sim -- Paper/Live panes follow the tab', () => {
    expect(simReplayTarget('IMCC', clock({ replay_source: 'none' }), false))
      .toEqual({ kind: 'ok' });
  });

  it('says nothing before the clock has been read, so nothing flashes on load', () => {
    expect(simReplayTarget('IMCC', null, true)).toEqual({ kind: 'ok' });
    expect(simReplayTarget('IMCC', undefined, true)).toEqual({ kind: 'ok' });
  });

  it('names the empty desk when no replay is loaded', () => {
    expect(simReplayTarget('IMCC', clock({ replay_source: 'none' }), true))
      .toEqual({ kind: 'none' });
    expect(simReplayTarget('IMCC', clock(), true)).toEqual({ kind: 'none' });
  });

  it('names the other symbol -- the tab that never fills however long you wait', () => {
    expect(
      simReplayTarget('IMCC', clock({ replay_source: 'historical', replay_symbol: 'SPY' }), true),
    ).toEqual({ kind: 'other-symbol', replaySymbol: 'SPY' });
  });

  it('is silent on the tab that IS the replay, case and padding aside', () => {
    expect(
      simReplayTarget(' spy ', clock({ replay_source: 'historical', replay_symbol: 'SPY' }), true),
    ).toEqual({ kind: 'ok' });
    expect(
      simReplayTarget('SPY', clock({ replay_source: 'capture', replay_symbol: 'spy' }), true),
    ).toEqual({ kind: 'ok' });
  });

  it('reports a failed selection as failed, never as "still loading"', () => {
    expect(
      simReplayTarget('SPY', clock({
        replay_source: 'none', replay_ok: false, replay_error: 'Capture is empty',
      }), true),
    ).toEqual({ kind: 'failed', error: 'Capture is empty' });
  });

  it('stays silent when a loaded replay has not published its symbol yet', () => {
    expect(simReplayTarget('IMCC', clock({ replay_source: 'capture', replay_symbol: null }), true))
      .toEqual({ kind: 'ok' });
  });
});

describe('simRailNote', () => {
  it('lets the normal panes render outside Sim', () => {
    expect(simRailNote('IMCC', clock({ replay_source: 'none' }), false)).toBeNull();
  });

  it('says loading before the clock is read, rather than flashing LIVE panes', () => {
    expect(simRailNote('IMCC', null, true)).toBe('Loading replay...');
  });

  it('names the empty desk and the other symbol instead of the live panes', () => {
    expect(simRailNote('IMCC', clock({ replay_source: 'none' }), true))
      .toBe('No replay loaded -- no quote, Level 2 or Time & Sales.');
    expect(simRailNote('imcc', clock({ replay_source: 'historical', replay_symbol: 'SPY' }), true))
      .toBe('SPY is the loaded replay -- no IMCC quote, Level 2 or Time & Sales.');
    expect(simRailNote('SPY', clock({ replay_source: 'none', replay_ok: false, replay_error: 'x' }), true))
      .toBe('Replay failed to load -- nothing to show.');
  });

  it('keeps the normal panes for a CAPTURE of this symbol -- the backend feeds them the recording', () => {
    expect(simRailNote('SPY', clock({ replay_source: 'capture', replay_symbol: 'SPY' }), true)).toBeNull();
  });

  it('holds a loading note while a historical snapshot for this symbol is still on its way', () => {
    expect(simRailNote('SPY', clock({ replay_source: 'historical', replay_symbol: 'SPY' }), true))
      .toBe('Loading replay...');
  });
});

describe('simEmptyQuoteDetail', () => {
  const live = {
    symbol: 'IMCC', asset: { name: 'IMCC Corp' }, listing: { any: 1 }, halt: { halted: true },
    avg_volume: 5, rel_volume: 2, rvol_5min: 3, volume_in_5min: 4, news: [{ id: 1 }],
    fundamentals: { float_shares: 480_200 }, mode: 'live',
    snapshot: { latest_trade: { price: 1.74 }, daily_bar: { close: 1.74 } },
  } as unknown as TickerDetail;

  it("drops everything that is today's, keeps what is this ticker's identity", () => {
    const blank = simEmptyQuoteDetail(live, ' imcc ');
    expect(blank.symbol).toBe('IMCC');
    expect(blank.snapshot.latest_trade).toBeNull();
    expect(blank.snapshot.daily_bar).toBeNull();
    expect([blank.halt, blank.listing, blank.rel_volume, blank.mode]).toEqual([null, null, null, null]);
    expect(blank.news).toEqual([]);
    expect(blank.fundamentals).toEqual({ float_shares: 480_200 });
  });

  it("does not borrow another ticker's fundamentals", () => {
    expect(simEmptyQuoteDetail(live, 'SPY').fundamentals).toBeNull();
  });
});
