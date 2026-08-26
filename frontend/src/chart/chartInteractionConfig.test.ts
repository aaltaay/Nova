import { CrosshairMode } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { CHART_CROSSHAIR_OPTIONS } from './chartInteractionConfig';

describe('chart interaction config', () => {
  it('keeps drawing anchors at the cursor price instead of magnetizing to candle close', () => {
    expect(CHART_CROSSHAIR_OPTIONS.mode).toBe(CrosshairMode.Normal);
  });
});
