/**
 * Where the Ahead panel opens (ADR 065): never over the 1-minute pane -- its candles, zone, chips or price axis.
 */
import { describe, expect, it } from 'vitest';
import { SHEET_DOCK_MAX_SHARE, SHEET_GAP_PX, SHEET_MAX_PX, SHEET_MIN_PX, sheetPlace } from './aheadSheetPlace';

/** A 2x2 chart grid 1400 px wide; the 1-minute pane is the bottom-right one (x 700-1400). */
const GRID = { left: 0, right: 1400 };
const BOTTOM_RIGHT = { left: 1150, right: 1400, paneLeft: 700, paneRight: 1400 };

describe('the Ahead panel placement', () => {
  it('slides over the other panes when the 1-minute pane is the bottom-right one, clear of all of it', () => {
    const p = sheetPlace(GRID, BOTTOM_RIGHT);
    expect(p).toEqual({ side: 'left', width: SHEET_MAX_PX, dock: false });
    expect(GRID.left + p.width).toBeLessThanOrEqual(BOTTOM_RIGHT.paneLeft - SHEET_GAP_PX);
  });

  it('opens on the right when the 1-minute pane is on the left', () => {
    const p = sheetPlace(GRID, { left: 300, right: 700, paneLeft: 0, paneRight: 700 });
    expect(p.side).toBe('right');
    expect(p.dock).toBe(false);
    expect(GRID.right - p.width).toBeGreaterThanOrEqual(700 + SHEET_GAP_PX);
  });

  it('narrows to the room beside the 1-minute pane', () => {
    expect(sheetPlace(GRID, { left: 1150, right: 1400, paneLeft: 408, paneRight: 1400 }))
      .toEqual({ side: 'left', width: 400, dock: false });
  });

  it('docks beside the charts, away from the zone, when the 1-minute pane fills the grid', () => {
    const wide = { left: 0, right: 1920 };
    const p = sheetPlace(wide, { left: 1240, right: 1920, paneLeft: 0, paneRight: 1920 });
    expect(p).toEqual({ side: 'left', width: SHEET_MAX_PX, dock: true });
    const small = sheetPlace(GRID, { left: 1000, right: 1400, paneLeft: 0, paneRight: 1400 });
    expect(small).toEqual({ side: 'left', width: 1400 * SHEET_DOCK_MAX_SHARE, dock: true });
    expect(sheetPlace({ left: 0, right: 600 }, { left: 400, right: 600, paneLeft: 0, paneRight: 600 }).width)
      .toBe(SHEET_MIN_PX);
  });

  it('stays docked once the dock has squeezed the pane (the answer never flips)', () => {
    const wide = { left: 0, right: 1920 };
    const dock = sheetPlace(wide, { left: 1240, right: 1920, paneLeft: 0, paneRight: 1920 });
    // Docked left, the pane now spans 520-1920 and its zone moved right with the squeeze.
    const squeezed = { left: 1500, right: 1920, paneLeft: SHEET_MAX_PX, paneRight: 1920 };
    expect(sheetPlace(wide, squeezed, dock)).toEqual(dock);
  });

  it('opens on the right at its usual width with no zone on screen', () => {
    expect(sheetPlace(GRID, null)).toEqual({ side: 'right', width: SHEET_MAX_PX, dock: false });
    expect(sheetPlace({ left: 0, right: 600 }, null).width).toBeCloseTo(600 * 0.62);
  });
});
