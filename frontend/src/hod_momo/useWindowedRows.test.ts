import { describe, expect, it } from 'vitest';
import { computeWindowSlice } from './useWindowedRows';

describe('computeWindowSlice', () => {
  it('windows a large list to visible + overscan indices', () => {
    const s = computeWindowSlice(2000, 0, 36, 14, 6);
    expect(s.startIndex).toBe(0);
    expect(s.endIndex).toBe(20);
    expect(s.offsetTop).toBe(0);
    expect(s.offsetBottom).toBe((2000 - 20) * 36);
  });

  it('advances the window on scroll', () => {
    const s = computeWindowSlice(500, 36 * 100, 36, 14, 6);
    expect(s.startIndex).toBe(94);
    expect(s.endIndex).toBe(120);
    expect(s.offsetTop).toBe(94 * 36);
  });

  it('clamps at the end of the list', () => {
    const s = computeWindowSlice(30, 36 * 40, 36, 14, 6);
    expect(s.endIndex).toBe(30);
    expect(s.offsetBottom).toBe(0);
  });
});
