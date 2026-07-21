import { describe, expect, it } from 'vitest';
import { computeVisibleRowRange } from './HodMomoAlertTable';

describe('computeVisibleRowRange', () => {
  it('mounts only the top viewport + overscan when scrolled to the top', () => {
    const range = computeVisibleRowRange(0, 5_000, 32, 960, 12);
    expect(range.startIndex).toBe(0);
    // viewportHeight 960 / rowHeight 32 = 30 visible rows + 12 overscan below.
    expect(range.endIndex).toBe(30 + 12);
    expect(range.topSpacerPx).toBe(0);
    expect(range.bottomSpacerPx).toBe((5_000 - (30 + 12)) * 32);
  });

  it('mounts a bounded window in the middle of a huge list, never the whole list', () => {
    const range = computeVisibleRowRange(32_000, 5_000, 32, 960, 12);
    // 32000 / 32 = row 1000 is first visible.
    expect(range.startIndex).toBe(1000 - 12);
    expect(range.endIndex).toBe(1000 + 30 + 12);
    expect(range.endIndex - range.startIndex).toBe(30 + 24);
    expect(range.topSpacerPx).toBe(range.startIndex * 32);
    expect(range.bottomSpacerPx).toBe((5_000 - range.endIndex) * 32);
  });

  it('clamps the end of the window at the last row without overscanning past it', () => {
    // firstVisible=4980; 4980 + 30 visible + 12 overscan = 5022 > total, so
    // endIndex clamps at 5000 instead of running past the list.
    const range = computeVisibleRowRange(4_980 * 32, 5_000, 32, 960, 12);
    expect(range.endIndex).toBe(5_000);
    expect(range.bottomSpacerPx).toBe(0);
    expect(range.startIndex).toBeLessThan(5_000);
  });

  it('clamps the start of the window at row 0 without a negative overscan', () => {
    const range = computeVisibleRowRange(5, 5_000, 32, 960, 12);
    expect(range.startIndex).toBe(0);
    expect(range.topSpacerPx).toBe(0);
  });

  it('returns an empty range for an empty list', () => {
    expect(computeVisibleRowRange(0, 0, 32, 960, 12)).toEqual({
      startIndex: 0,
      endIndex: 0,
      topSpacerPx: 0,
      bottomSpacerPx: 0,
    });
  });

  it('keeps the mounted row count flat whether the list has 100 or 100,000 rows', () => {
    const small = computeVisibleRowRange(0, 100, 32, 960, 12);
    const huge = computeVisibleRowRange(0, 100_000, 32, 960, 12);
    expect(huge.endIndex - huge.startIndex).toBe(small.endIndex - small.startIndex);
  });
});
