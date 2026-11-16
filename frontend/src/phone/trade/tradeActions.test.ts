import { describe, expect, it } from 'vitest';
import { PROTECTIVE_KINDS } from '../../hotkeys/runNovaAction';
import {
  buyLimit,
  buyLimitPrice,
  buyMarket,
  cancelAll,
  flatten,
  priceWord,
  sellAtAsk,
  sellAtBid,
  sellShares,
  stepQty,
} from './tradeActions';

describe('the phone ticket buttons are the desk\'s own actions', () => {
  it('names each button as one desk action kind with its numbers', () => {
    expect(buyMarket(500)).toMatchObject({ kind: 'buy_market', params: { shares: 500 }, enabled: true });
    expect(buyLimit(500)).toMatchObject({ kind: 'buy_limit_ask_offset', params: { shares: 500, offsetDollars: 0.05, outsideRth: true } });
    expect(sellAtAsk(50)).toMatchObject({ kind: 'sell_pos_pct_ask', params: { percent: 50, offsetDollars: 0 } });
    expect(sellAtBid(100)).toMatchObject({ kind: 'sell_pos_pct_bid_offset', params: { percent: 100, offsetDollars: 0.03 } });
  });

  it('flatten and cancel-all are the kinds the padlock never holds', () => {
    expect(PROTECTIVE_KINDS[flatten().kind]).toBe('flatten');
    expect(PROTECTIVE_KINDS[cancelAll().kind]).toBe('cancel');
    // An ordinary sell is not one of them: it answers to the padlock, as on the desk.
    expect(PROTECTIVE_KINDS[sellAtBid(100).kind]).toBeUndefined();
  });

  it('writes on a button what the desk would send', () => {
    expect(buyLimitPrice(4.82)).toBe(4.87);
    expect(buyLimitPrice(0.3456)).toBe(0.3956);
    expect(buyLimitPrice(null)).toBeNull();
    expect(priceWord(4.8)).toBe('4.80');
    expect(priceWord(null)).toBe('—');
    expect(sellShares(500, 50)).toBe(250);
    expect(sellShares(501, 50)).toBe(250);
    expect(sellShares(500, 100)).toBe(500);
    // One share has no half; flat or short has nothing to sell.
    expect(sellShares(1, 50)).toBeNull();
    expect(sellShares(0, 100)).toBeNull();
    expect(sellShares(-300, 100)).toBeNull();
  });

  it('steps a share count by 1, 10 or 100, and never under 1', () => {
    expect(stepQty(100, 1)).toBe(200);
    expect(stepQty(100, -1)).toBe(90);
    expect(stepQty(500, -1)).toBe(400);
    expect(stepQty(10, -1)).toBe(9);
    expect(stepQty(9, 1)).toBe(10);
    expect(stepQty(50, 1)).toBe(60);
    expect(stepQty(1, -1)).toBe(1);
    expect(stepQty(0, 1)).toBe(1);
  });
});
