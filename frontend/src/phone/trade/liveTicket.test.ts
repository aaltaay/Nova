/**
 * The ticket's Live words (ADR 070 amendment 2026-11-20): a button says what the door will send, under the desk's
 * own Live share limit, and never offers a size the door would cut.
 */
import { describe, expect, it } from 'vitest';
import { QUICK_SIZES, limitBinds, liveLimitWords, liveSellWords, quickSizeUnder, shareCount, sizesUnder, underCap } from './liveTicket';

describe('the sizes a Live ticket offers', () => {
  it('offers every Quick size on Paper and Sim, where no limit is read', () => {
    expect(limitBinds(null)).toBe(false);
    expect(sizesUnder(null)).toEqual([...QUICK_SIZES]);
  });

  it("offers one share at the desk's default Live limit, as the frozen board draws it", () => {
    expect(limitBinds(1)).toBe(true);
    expect(sizesUnder(1)).toEqual([1]);
    expect(quickSizeUnder(500, 1)).toBe(1);
  });

  it('offers the sizes under a raised limit, and the limit itself', () => {
    expect(sizesUnder(300)).toEqual([100, 300]);
    expect(sizesUnder(1000)).toEqual([100, 500, 1000]);
    expect(quickSizeUnder(100, 300)).toBe(100);
    // A size the row no longer shows gives way to the biggest one under it.
    expect(quickSizeUnder(500, 300)).toBe(300);
    expect(quickSizeUnder(700, 1000)).toBe(500);
  });

  it('never defaults real money to the limit: a size under every offered one takes the smallest', () => {
    // The phone's first Live size is 1; a raised limit starts it at 100, never at 1,000.
    expect(quickSizeUnder(1, 1000)).toBe(100);
    expect(quickSizeUnder(1, 300)).toBe(100);
    expect(quickSizeUnder(1, 1)).toBe(1);
  });

  it('keeps the chosen size under a limit too big to bind, and cuts only what passes it', () => {
    expect(limitBinds(5000)).toBe(false);
    expect(sizesUnder(5000)).toEqual([...QUICK_SIZES]);
    expect(quickSizeUnder(1000, 5000)).toBe(1000);
    expect(quickSizeUnder(1000, null)).toBe(1000);
  });
});

describe('what a Live button says it sends', () => {
  it('cuts an order to the limit, and leaves it whole without one', () => {
    expect(underCap(5, 1)).toBe(1);
    expect(underCap(1, 1)).toBe(1);
    expect(underCap(5, null)).toBe(5);
  });

  it('says the share that goes when the limit cuts a sell, the frozen Live board\'s words', () => {
    expect(liveSellWords(500, 1)).toBe('LIVE SELL 1');
    expect(liveSellWords(250, 1)).toBe('LIVE SELL 1');
    expect(liveSellWords(500, 300)).toBe('LIVE SELL 300');
  });

  it('says the whole sell when the limit lets it through', () => {
    expect(liveSellWords(1, 1)).toBe('LIVE SELL 1');
    expect(liveSellWords(250, 300)).toBe('LIVE SELL 250');
    expect(liveSellWords(1200, null)).toBe('LIVE SELL 1,200');
  });

  it("names the desk's limit and where it is raised", () => {
    expect(liveLimitWords(1)).toBe('Live limit: 1 share. Raise it on the desk.');
    expect(liveLimitWords(300)).toBe('Live limit: 300 shares. Raise it on the desk.');
    expect(shareCount(1000)).toBe('1,000');
  });
});
