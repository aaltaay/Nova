import { describe, expect, it } from 'vitest';
import { feedFromPayload } from './reviewFeed';
import type { ReviewPayload } from './reviewFixture';

function payload(source: string, frames: ReviewPayload['timeframes']): ReviewPayload {
  return {
    ok: true,
    schema_version: 1,
    symbol: 'IMCC',
    date: '2026-09-18',
    as_of: '16:00',
    as_of_iso: '2026-09-18T16:00:00-04:00',
    source,
    lookahead: false,
    vwap_anchor: '04:00',
    timeframes: frames,
    levels: {} as ReviewPayload['levels'],
    setups: [],
  };
}

describe('feedFromPayload pane notes', () => {
  it('names the 10s pane by its real source -- the Massive tape, never IBKR', () => {
    const feed = feedFromPayload(payload('front-door', {
      '10s': { bars: [], source: 'massive-trades' },
      '1m': { bars: [], source: 'massive-minutes' },
      '5m': { bars: [], source: 'massive-minutes' },
      '1d': { bars: [], source: 'massive-daily' },
    }));
    expect(feed.notes?.['10Sec']).toBe('10s · Massive tape -- built from the consolidated trades');
    expect(feed.notes?.['1Min']).toBe('1m · Massive minute bars');
    expect(feed.notes?.['5Min']).toBe('5m · Massive minute bars');
    expect(feed.notes?.['1Day']).toMatch(/^1d · Massive daily bars/);
    expect(Object.values(feed.notes ?? {}).join(' ')).not.toMatch(/IBKR|live tape/);
  });

  it('claims no source when the payload names none, and labels the sample as a sample', () => {
    expect(feedFromPayload(payload('front-door', { '10s': { bars: [] } })).notes).toEqual({});
    expect(feedFromPayload(payload('fixture', { '10s': { bars: [] } })).notes?.['10Sec'])
      .toBe('Sample -- not a recorded day');
  });
});
