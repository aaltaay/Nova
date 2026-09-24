import { describe, expect, it } from 'vitest';
import { L2_DAS_TIER_COLORS } from '../constants';
import {
  assignPriceTiers,
  bookPeak,
  maxSize,
  padLevels,
  sizeGaugePct,
  tierBackground,
} from './dasDepthTiers';
import type { DepthLevel } from './types';

function lvl(price: number, size: number, side: 'bid' | 'ask' = 'bid'): DepthLevel {
  return { price, size, side, mm: 'ISLAND' };
}

describe('assignPriceTiers', () => {
  it('keeps same price on the same DAS color tier', () => {
    expect(assignPriceTiers([lvl(10, 100), lvl(10, 200), lvl(9.9, 50)])).toEqual([0, 0, 1]);
  });

  it('advances tier on each new price', () => {
    expect(assignPriceTiers([lvl(5, 1), lvl(4, 1), lvl(3, 1)])).toEqual([0, 1, 2]);
  });
});

describe('tierBackground', () => {
  it('uses one shared rainbow palette for bid and ask tiers', () => {
    expect(tierBackground(0)).toBe(L2_DAS_TIER_COLORS[0]);
    expect(tierBackground(1)).toBe(L2_DAS_TIER_COLORS[1]);
    expect(tierBackground(L2_DAS_TIER_COLORS.length)).toBe(L2_DAS_TIER_COLORS[0]);
  });
});

describe('padLevels', () => {
  it('pads to fixed montage height', () => {
    const padded = padLevels([lvl(1, 10)], 3);
    expect(padded).toHaveLength(3);
    expect(padded[0]?.price).toBe(1);
    expect(padded[1]).toBeNull();
  });
});

describe('maxSize', () => {
  it('returns peak size for heat bars', () => {
    expect(maxSize([lvl(1, 10), lvl(2, 400), lvl(3, 50)])).toBe(400);
  });
});

describe('bookPeak', () => {
  it('takes the largest size on either side, so both gauges share one scale', () => {
    expect(bookPeak([lvl(4.78, 3001), lvl(4.8, 500)], [lvl(5.18, 722, 'ask')])).toBe(3001);
    expect(bookPeak([], [lvl(5.18, 722, 'ask')])).toBe(722);
    expect(bookPeak([], [])).toBe(0);
  });
});

describe('sizeGaugePct', () => {
  it('measures a level against the book-wide peak', () => {
    expect(sizeGaugePct(3001, 3001)).toBe(100);
    expect(sizeGaugePct(722, 3001)).toBe(24.1);
    expect(sizeGaugePct(100, 3001)).toBe(3.3);
  });

  it('draws nothing without a size or a peak', () => {
    expect(sizeGaugePct(0, 3001)).toBe(0);
    expect(sizeGaugePct(100, 0)).toBe(0);
    expect(sizeGaugePct(Number.NaN, 3001)).toBe(0);
  });

  it('never runs past the row', () => {
    expect(sizeGaugePct(5000, 3001)).toBe(100);
  });
});
