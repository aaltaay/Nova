import { describe, expect, it } from 'vitest';
import {
  computeTapeVisibleRange,
  tapePinnedToNewest,
  tapeScrollAfterPrepend,
} from './tapeWindow';

describe('computeTapeVisibleRange', () => {
  it('windows only the viewport plus overscan over the full ring', () => {
    const range = computeTapeVisibleRange(0, 200, 22, 220, 4);
    // 220/22 = 10 visible, +4 overscan => 14 mounted; ring stays 200.
    expect(range.startIndex).toBe(0);
    expect(range.endIndex).toBe(14);
    expect(range.topSpacerPx).toBe(0);
    expect(range.bottomSpacerPx).toBe((200 - 14) * 22);
    expect(range.endIndex - range.startIndex).toBeLessThan(200);
  });

  it('scrolls into the middle of the ring without dropping ring length', () => {
    const range = computeTapeVisibleRange(22 * 40, 200, 22, 110, 2);
    expect(range.startIndex).toBe(38);
    expect(range.endIndex).toBe(47);
    expect(range.topSpacerPx).toBe(38 * 22);
    expect(range.bottomSpacerPx).toBe((200 - 47) * 22);
  });

  it('returns an empty window for an empty ring', () => {
    expect(computeTapeVisibleRange(0, 0, 22, 220, 4)).toEqual({
      startIndex: 0,
      endIndex: 0,
      topSpacerPx: 0,
      bottomSpacerPx: 0,
    });
  });
});

describe('tapeScrollAfterPrepend', () => {
  it('keeps the newest-pinned viewport at scrollTop 0', () => {
    expect(tapeScrollAfterPrepend(0, 7, 22, 4)).toBe(0);
    expect(tapePinnedToNewest(0)).toBe(true);
  });

  it('shifts an older-print viewport down by the prepended row height', () => {
    expect(tapeScrollAfterPrepend(220, 3, 22, 4)).toBe(220 + 66);
    expect(tapePinnedToNewest(220)).toBe(false);
  });
});
