import { describe, expect, it } from 'vitest';
import { L2_SPREAD_WIDE_DOLLARS } from '../constants';
import { computeL2Heuristics } from './l2Heuristics';
import type { DepthBook } from './types';

function book(bidSize: number, askSize: number, spread = 0.01): DepthBook {
  const mid = 10;
  return {
    bids: [{ price: mid, size: bidSize, side: 'bid', mm: 'OVERNIGHT' }],
    asks: [{ price: mid + spread, size: askSize, side: 'ask', mm: 'OVERNIGHT' }],
    l1_fallback: false,
  };
}

describe('computeL2Heuristics', () => {
  it('flags ask stacked when ask size dominates', () => {
    const h = computeL2Heuristics(book(100, 400));
    expect(h.askStacked).toBe(true);
    expect(h.bidHeavy).toBe(false);
  });

  it('flags bid heavy when bid size dominates', () => {
    const h = computeL2Heuristics(book(400, 100));
    expect(h.bidHeavy).toBe(true);
    expect(h.askStacked).toBe(false);
  });

  it('flags wide spread using the shared dollar threshold', () => {
    const h = computeL2Heuristics(book(100, 100, L2_SPREAD_WIDE_DOLLARS));
    expect(h.wideSpread).toBe(true);
  });

  it('handles thin overnight books without throwing', () => {
    const h = computeL2Heuristics(book(10, 10, 0.05));
    expect(h).toEqual({
      askStacked: false,
      bidHeavy: false,
      wideSpread: true,
    });
  });
});
