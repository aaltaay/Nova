/**
 * T&S DOM window over the full print ring. The ring still holds every
 * capped print; only the viewport (+ overscan) is mounted.
 */
import {
  TAPE_OVERSCAN_ROWS,
  TAPE_ROW_HEIGHT_PX,
  TAPE_STICK_TOP_PX,
} from '../constants';

export interface TapeVisibleRange {
  startIndex: number;
  /** Exclusive. */
  endIndex: number;
  topSpacerPx: number;
  bottomSpacerPx: number;
}

export function computeTapeVisibleRange(
  scrollTop: number,
  total: number,
  rowHeight: number = TAPE_ROW_HEIGHT_PX,
  viewportHeight: number = rowHeight,
  overscan: number = TAPE_OVERSCAN_ROWS,
): TapeVisibleRange {
  if (total <= 0 || rowHeight <= 0) {
    return { startIndex: 0, endIndex: 0, topSpacerPx: 0, bottomSpacerPx: 0 };
  }
  const firstVisible = Math.floor(Math.max(0, scrollTop) / rowHeight);
  const visibleRowCount = Math.max(1, Math.ceil(Math.max(0, viewportHeight) / rowHeight));
  const startIndex = Math.max(0, firstVisible - overscan);
  const endIndex = Math.min(total, firstVisible + visibleRowCount + overscan);
  return {
    startIndex,
    endIndex,
    topSpacerPx: startIndex * rowHeight,
    bottomSpacerPx: (total - endIndex) * rowHeight,
  };
}

/** Newest-first tape: stay at top, or shift scroll when older rows are prepended. */
export function tapeScrollAfterPrepend(
  scrollTop: number,
  addedCount: number,
  rowHeight: number = TAPE_ROW_HEIGHT_PX,
  stickPx: number = TAPE_STICK_TOP_PX,
): number {
  if (addedCount <= 0 || scrollTop <= stickPx) return scrollTop;
  return scrollTop + addedCount * rowHeight;
}

export function tapePinnedToNewest(
  scrollTop: number,
  stickPx: number = TAPE_STICK_TOP_PX,
): boolean {
  return scrollTop <= stickPx;
}
