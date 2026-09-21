import { describe, expect, it } from 'vitest';
import { simReplayTarget } from './simReplayTarget';
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
