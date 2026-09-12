import { describe, expect, it } from 'vitest';
import {
  CHART_POSITION_TAG_FALLBACK_Y_RATIO,
  CHART_POSITION_TAG_RIGHT_GAP_PX,
} from './positionOverlayConstants';
import { positionTagPlacement } from './positionTagLayout';

describe('positionTagPlacement', () => {
  it('pins to the avg-cost y when the line is on-screen', () => {
    expect(
      positionTagPlacement({ y: 42, paneHeight: 200, priceScaleWidth: 50 }),
    ).toEqual({
      top: 42,
      right: 50 + CHART_POSITION_TAG_RIGHT_GAP_PX,
      offScale: false,
    });
  });

  it('falls back when the series has no coordinate (empty sample chart)', () => {
    expect(
      positionTagPlacement({ y: null, paneHeight: 200, priceScaleWidth: 0 }),
    ).toEqual({
      top: 200 * CHART_POSITION_TAG_FALLBACK_Y_RATIO,
      right: CHART_POSITION_TAG_RIGHT_GAP_PX,
      offScale: true,
    });
  });

  it('treats a y above the pane as off-scale', () => {
    const next = positionTagPlacement({
      y: 400,
      paneHeight: 200,
      priceScaleWidth: 10,
    });
    expect(next.offScale).toBe(true);
    expect(next.top).toBe(200 * CHART_POSITION_TAG_FALLBACK_Y_RATIO);
  });
});
