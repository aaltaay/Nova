import { describe, expect, it } from 'vitest';
import { TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON } from '../constants';
import { marketOrdersRefusedNow } from './marketOutsideRth';

// 2026-09-21 is a Monday; 2026-09-19 a Saturday. Offsets are EDT.
const at = (iso: string) => new Date(iso);

describe('marketOrdersRefusedNow (MKT_OUTSIDE_RTH preflight)', () => {
  it('allows Market inside weekday regular hours', () => {
    expect(marketOrdersRefusedNow('live', at('2026-09-21T10:00:00-04:00'))).toBeNull();
    expect(marketOrdersRefusedNow('paper', at('2026-09-21T15:59:00-04:00'))).toBeNull();
  });

  it('refuses Market after the close, premarket and on a weekend, with the backend\'s words', () => {
    expect(marketOrdersRefusedNow('paper', at('2026-09-21T17:10:00-04:00'))).toBe(TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON);
    expect(marketOrdersRefusedNow('live', at('2026-09-21T08:00:00-04:00'))).toBe(TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON);
    expect(marketOrdersRefusedNow('live', at('2026-09-19T10:30:00-04:00'))).toBe(TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON);
  });

  it('stays quiet on Sim -- the replay playhead is the clock and only the backend reads it', () => {
    expect(marketOrdersRefusedNow('sim', at('2026-09-21T17:10:00-04:00'))).toBeNull();
  });
});
