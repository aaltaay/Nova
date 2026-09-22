/**
 * The practice ledger's BP rule on the ticket (QA W28): mirrors backend
 * practice/fees.py and practice/margin.py so "BP after" is not BP +/- value.
 */
import { describe, expect, it } from 'vitest';
import {
  practiceBuyingPowerAfter,
  practiceCommission,
  practiceFees,
  practiceMultiplier,
} from './practiceBuyingPower';

describe('practice fees (backend practice/fees.py)', () => {
  it('IBKR Fixed: per share, a $1 minimum, capped at 1% of value -- the cap wins', () => {
    expect(practiceCommission(100, 1.49)).toBe(1); // 0.50 -> the $1 minimum
    expect(practiceCommission(1000, 10)).toBe(5);
    expect(practiceCommission(10, 1)).toBeCloseTo(0.1, 9); // 1% of $10 beats the minimum
  });

  it('SEC and FINRA TAF on sells only', () => {
    expect(practiceFees('BUY', 100, 1.49)).toBe(1);
    expect(practiceFees('SELL', 100, 1.47)).toBeCloseTo(1 + 147 * 0.0000206 + 100 * 0.000195, 9);
  });
});

describe('practiceBuyingPowerAfter (backend practice/margin.py)', () => {
  it('a buy costs its commission out of equity and adds its value to gross', () => {
    const bp = practiceBuyingPowerAfter({
      netLiquidation: 100_020, grossPositionValue: 507, side: 'BUY', qty: 100, price: 1.49, heldQty: 0, heldMark: null,
    });
    expect(bp).toBeCloseTo((100_020 - 1) * 4 - (507 + 149), 6);
  });

  it('a closing sell frees the position at its mark and pays the sell-side fees', () => {
    const fees = practiceFees('SELL', 100, 1.47);
    const bp = practiceBuyingPowerAfter({
      netLiquidation: 100_020, grossPositionValue: 507, side: 'SELL', qty: 100, price: 1.47, heldQty: 100, heldMark: 1.52,
    });
    // equity' = 100,020 + 100 x (1.47 - 1.52) - fees; gross' = 507 - 152 + 0
    expect(bp).toBeCloseTo((100_020 - 5 - fees) * 4 - (507 - 152), 6);
  });

  it('below the PDT line the multiplier is Reg T 2x, and never below zero', () => {
    expect(practiceMultiplier(24_999)).toBe(2);
    expect(practiceMultiplier(25_000)).toBe(4);
    expect(practiceBuyingPowerAfter({
      netLiquidation: 1_000, grossPositionValue: 1_900, side: 'BUY', qty: 100, price: 5, heldQty: 0, heldMark: null,
    })).toBe(0);
  });

  it('is unknown without the account figures', () => {
    expect(practiceBuyingPowerAfter({
      netLiquidation: null, grossPositionValue: 0, side: 'BUY', qty: 1, price: 1, heldQty: 0, heldMark: null,
    })).toBeNull();
  });
});
