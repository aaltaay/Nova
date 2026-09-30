import { describe, expect, it } from 'vitest';
import { SAMPLE_CRYPTO_BOARD } from '../sampleCryptos';
import type { BridgeRow } from '../types';
import { tipBeta, tipLane, tipRead, tipSince } from './glossaryDesk';
import { fundingWords, tipLiquidations, tipSpot, tipWhy } from './glossaryMarket';

const row = (over: Partial<BridgeRow>): BridgeRow => ({
  symbol: 'MARA', what: 'Miner', driver: 'BTC', beta: 2.4, close: 21.34, last: 23, since_close_pct: 7.8,
  implied_pct: 5.1, read: 'ahead', gap_pt: 2.7, ...over,
});

describe('the hover cards say what a number means, and when it is unknown', () => {
  it('reads funding in words at the page thresholds', () => {
    expect(fundingWords(0.045)).toBe('longs are crowded');
    expect(fundingWords(-0.02)).toBe('shorts are crowded');
    expect(fundingWords(0.01)).toBe('calm');
    expect(fundingWords(null)).toBe('unknown');
  });

  it('reads a stock ahead, behind, in line or unknown against the coin', () => {
    expect(tipRead(row({})).now).toBe('MARA is ahead by 2.7 points: MARA already moved more than BTC implies.');
    expect(tipRead(row({ read: 'behind', gap_pt: -1.3 })).now).toContain('behind by 1.3 points');
    expect(tipRead(row({ read: 'in_line', gap_pt: 0.2 })).now).toContain('in line (within 0.5 points)');
    expect(tipRead(row({ read: null, since_close_pct: null })).now).toContain('unknown until both numbers are known');
  });

  it('never calls a missing print or beta zero', () => {
    expect(tipSince(row({ since_close_pct: null }), 'after_hours').now).toBe('No trade since the close yet: unknown, not zero.');
    const beta = tipBeta(row({ beta: null }));
    expect(beta.title).toBe('Beta unknown');
    expect(beta.visual).toBeUndefined();
    expect(beta.now).toContain('20 sessions');
  });

  it('states the absences in the words the tiles use', () => {
    expect(tipLiquidations(null).now).toBe('Not known on this desk.');
    const pepe = SAMPLE_CRYPTO_BOARD.coins.find((c) => c.symbol === 'PEPE')!;
    expect(tipSpot(pepe).title).toBe('PEPE: watch only');
    expect(tipSpot({ ...pepe, ibkr: null }).now).toBe('Not asked yet: IBKR is not connected.');
    expect(tipWhy({ ...pepe, why: null, news_checked: false }).now).toBe('Unknown: no news source has answered yet.');
    expect(tipWhy({ ...pepe, why: null, news_checked: true }).now).toContain('No news found in the last 24 hours');
  });

  it('names the funding settlements in ET from the board clock', () => {
    const t = tipLane('funding', SAMPLE_CRYPTO_BOARD.clock);
    expect(t.what).toContain('00:00, 08:00 and 16:00 UTC (04:00, 12:00, 20:00 ET)');
    expect(t.visual).toMatchObject({ kind: 'sessions', highlight: ['funding', 'crypto'] });
  });
});
