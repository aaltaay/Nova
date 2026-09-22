import { describe, expect, it } from 'vitest';
import {
  SCANNER_MIN_REMAINING_PX,
  SIDE_PANEL_MIN_WIDTH_PX,
  SIDE_PANEL_RAIL_RESERVE_PX,
  SIDE_PANEL_WIDTH_PX,
} from '../constants';
import { clampSidePanelWidth } from './useSidePanelWidth';

describe('clampSidePanelWidth (QA V7: the board keeps every Scanner column)', () => {
  it('shrinks the 820 px default so the board keeps its minimum beside the rail', () => {
    const w = clampSidePanelWidth(SIDE_PANEL_WIDTH_PX, 1920);
    expect(w).toBe(1920 - SIDE_PANEL_RAIL_RESERVE_PX - SCANNER_MIN_REMAINING_PX);
    expect(1920 - SIDE_PANEL_RAIL_RESERVE_PX - w).toBeGreaterThanOrEqual(SCANNER_MIN_REMAINING_PX);
  });

  it('never goes under the panel minimum on a small screen', () => {
    expect(clampSidePanelWidth(SIDE_PANEL_WIDTH_PX, 1280)).toBe(SIDE_PANEL_MIN_WIDTH_PX);
  });

  it('keeps a wide stored panel on a wide screen', () => {
    expect(clampSidePanelWidth(900, 2560)).toBe(900);
  });
});
