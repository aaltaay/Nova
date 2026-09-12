import { describe, expect, it } from 'vitest';
import {
  CHART_POSITION_MENU_CLOSE,
  CHART_POSITION_MENU_VIEW_DETAILS,
} from './positionOverlayConstants';
import { chartPositionMenuItems } from './positionMenu';

describe('chartPositionMenuItems', () => {
  it('ships Close Position and View Trade Details only', () => {
    const items = chartPositionMenuItems();
    expect(items.map((row) => row.id)).toEqual(['close', 'view_details']);
    expect(items[0]?.label).toBe(CHART_POSITION_MENU_CLOSE);
    expect(items[1]?.label).toBe(CHART_POSITION_MENU_VIEW_DETAILS);
    expect(items.some((row) => /ticks|color|coming soon/i.test(row.label))).toBe(
      false,
    );
  });
});
