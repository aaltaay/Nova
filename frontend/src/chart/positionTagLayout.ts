/**
 * Place the clickable Long/Short badge over the avg-cost line.
 * Empty IBKR series (sample desk) has no coordinate -- fall back so the
 * fixture tag still demos the menu.
 */
import {
  CHART_POSITION_TAG_FALLBACK_Y_RATIO,
  CHART_POSITION_TAG_RIGHT_GAP_PX,
} from './positionOverlayConstants';

export interface PositionTagPlacement {
  top: number;
  right: number;
  offScale: boolean;
}

export function positionTagPlacement(input: {
  y: number | null;
  paneHeight: number;
  priceScaleWidth: number;
}): PositionTagPlacement {
  const height =
    Number.isFinite(input.paneHeight) && input.paneHeight > 0
      ? input.paneHeight
      : 160;
  const right =
    Math.max(0, Number(input.priceScaleWidth) || 0) +
    CHART_POSITION_TAG_RIGHT_GAP_PX;
  const y = input.y;
  const inView = y != null && Number.isFinite(y) && y >= 0 && y <= height;
  if (inView) {
    return { top: y, right, offScale: false };
  }
  return {
    top: height * CHART_POSITION_TAG_FALLBACK_Y_RATIO,
    right,
    offScale: true,
  };
}
