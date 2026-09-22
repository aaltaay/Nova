import { describe, expect, it } from 'vitest';
import {
  formatSeedPrice,
  seedLimitPrice,
  seedStopPrice,
  seedTrailAmount,
} from './tradeDefaultSeed';

describe('tradeDefaultSeed', () => {
  const book = { last: 10, bid: 9.9, ask: 10.1 };

  it('seeds ask for BUY and bid for SELL on ask_bid', () => {
    expect(seedLimitPrice('ask_bid', 'BUY', book)).toBe(10.1);
    expect(seedLimitPrice('ask_bid', 'SELL', book)).toBe(9.9);
  });

  it('falls back to last when book side missing', () => {
    expect(
      seedLimitPrice('ask_bid', 'BUY', { last: 10, bid: 9.9, ask: null }),
    ).toBe(10);
  });

  it('seeds mid and last', () => {
    expect(seedLimitPrice('mid', 'BUY', book)).toBeCloseTo(10);
    expect(seedLimitPrice('last', 'SELL', book)).toBe(10);
  });

  it('seeds a stop on the far side of the market for the order side (R18)', () => {
    // A BUY stop triggers on a rise, a SELL stop on a fall: neither is through the market.
    expect(seedStopPrice('BUY', 100, 1)).toBeCloseTo(101);
    expect(seedStopPrice('SELL', 100, 1)).toBeCloseTo(99);
    expect(seedStopPrice('BUY', null, 1)).toBeNull();
  });

  it('seeds trail $ from the stop offset percent', () => {
    expect(seedTrailAmount(100, 1)).toBeCloseTo(1);
    expect(seedTrailAmount(null, 1)).toBeNull();
  });

  it('formats prices', () => {
    expect(formatSeedPrice(10.1)).toBe('10.10');
    expect(formatSeedPrice(null)).toBe('');
  });
});
