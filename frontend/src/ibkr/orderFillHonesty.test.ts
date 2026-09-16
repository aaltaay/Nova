import { describe, expect, it } from 'vitest';
import {
  assertNoFailedPlusFilled,
  displayFilledQty,
  isFailedPlusFilledLie,
  isSoftOrderWarning,
} from './orderFillHonesty';

describe('orderFillHonesty', () => {
  it('zeros Inactive filled_qty that was copied from limit (ZTG)', () => {
    expect(
      displayFilledQty({
        status: 'Inactive',
        filled_qty: 1,
        filled_at: null,
      }),
    ).toBe(0);
    expect(isFailedPlusFilledLie('Inactive', 1)).toBe(true);
    expect(() => assertNoFailedPlusFilled('Inactive', 1)).toThrow(/Failed\+Filled/);
  });

  it('keeps a real fill on Filled', () => {
    expect(
      displayFilledQty({
        status: 'Filled',
        filled_qty: 1,
        filled_at: '2026-09-16T14:05:12.100Z',
      }),
    ).toBe(1);
    expect(isFailedPlusFilledLie('Filled', 1)).toBe(false);
  });

  it('does not treat 2109-alone as a reject modal', () => {
    expect(isSoftOrderWarning('Warning 2109: outsideRth ignored')).toBe(true);
    expect(
      isSoftOrderWarning('Error 201: No Opening Trades: Small Cap'),
    ).toBe(false);
  });
});
