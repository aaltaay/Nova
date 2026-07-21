import { describe, expect, it } from 'vitest';
import { buildMockClosedOrders } from '../closed_orders/mockClosedOrders';
import {
  closedFillProgressAcceptable,
  fillProgressCoherent,
  remainingShares,
  remainingSharesWhole,
} from './orderQtyMath';
import { buildMockWorkingOrders } from './mockWorkingOrders';

describe('orderQtyMath', () => {
  it('prefers broker remaining_qty', () => {
    expect(
      remainingShares({ qty: 100, filled_qty: 20, remaining_qty: 30 }),
    ).toBe(30);
  });

  it('trusts broker remaining when it disagrees with qty − filled', () => {
    // Policy: display + Fill now prefer IB remaining when present.
    expect(
      remainingShares({ qty: 100, filled_qty: 40, remaining_qty: 55 }),
    ).toBe(55);
    expect(
      remainingSharesWhole({ qty: 100, filled_qty: 40, remaining_qty: 55 }),
    ).toBe(55);
    expect(
      fillProgressCoherent({ qty: 100, filled_qty: 40, remaining_qty: 55 }),
    ).toBe(false);
  });

  it('falls back to qty − filled when remaining missing', () => {
    expect(
      remainingShares({ qty: 100, filled_qty: 40, remaining_qty: null }),
    ).toBe(60);
    expect(remainingShares({ qty: 100, filled_qty: 40 })).toBe(60);
  });

  it('clamps negative remaining / overfill to zero', () => {
    expect(
      remainingShares({ qty: 10, filled_qty: 12, remaining_qty: -3 }),
    ).toBe(0);
    expect(
      remainingShares({ qty: 10, filled_qty: 15, remaining_qty: null }),
    ).toBe(0);
  });

  it('floors fractional shares for Fill now', () => {
    expect(
      remainingSharesWhole({ qty: 10.9, filled_qty: 0, remaining_qty: 10.9 }),
    ).toBe(10);
    expect(
      remainingSharesWhole({ qty: 10.9, filled_qty: 0.4, remaining_qty: null }),
    ).toBe(10);
  });

  it('treats filled + remaining === qty as coherent', () => {
    expect(
      fillProgressCoherent({ qty: 50, filled_qty: 20, remaining_qty: 30 }),
    ).toBe(true);
    expect(
      fillProgressCoherent({ qty: 50, filled_qty: 20, remaining_qty: 25 }),
    ).toBe(false);
    // Missing remaining → not our job to fail.
    expect(
      fillProgressCoherent({ qty: 50, filled_qty: 20, remaining_qty: null }),
    ).toBe(true);
  });

  it('mock working partials stay coherent (filled + remaining = qty)', () => {
    for (const row of buildMockWorkingOrders('TEST')) {
      expect(fillProgressCoherent(row)).toBe(true);
      expect(remainingShares(row)).toBe(row.remaining_qty);
      expect((row.filled_qty ?? 0) + remainingShares(row)).toBe(row.qty);
    }
  });

  it('mock closed rows are acceptable (incl. partial-cancel remaining 0)', () => {
    for (const row of buildMockClosedOrders('TEST')) {
      expect(closedFillProgressAcceptable(row)).toBe(true);
    }
    // Classic cancel-after-partial: filled 35 / qty 100 / remaining 0.
    expect(
      closedFillProgressAcceptable({
        qty: 100,
        filled_qty: 35,
        remaining_qty: 0,
      }),
    ).toBe(true);
    expect(
      fillProgressCoherent({ qty: 100, filled_qty: 35, remaining_qty: 0 }),
    ).toBe(false);
  });
});
