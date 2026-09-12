import { describe, expect, it } from 'vitest';
import {
  chartContextMenuPosition,
  chartSubmenuPosition,
} from './chartContextMenuPosition';

const VIEW = { viewportWidth: 1000, viewportHeight: 800 };

describe('chartContextMenuPosition', () => {
  it('opens down-right of the cursor when there is room', () => {
    expect(
      chartContextMenuPosition({
        x: 200,
        y: 120,
        menuWidth: 236,
        menuHeight: 260,
        ...VIEW,
      }),
    ).toEqual({ top: 120, left: 200 });
  });

  it('flips left of the cursor near the right edge', () => {
    const pos = chartContextMenuPosition({
      x: 960,
      y: 100,
      menuWidth: 236,
      menuHeight: 260,
      ...VIEW,
    });
    expect(pos.left).toBe(724);
    expect(pos.left + 236).toBeLessThanOrEqual(1000);
  });

  it('lifts the menu so the bottom rows stay on screen', () => {
    const pos = chartContextMenuPosition({
      x: 100,
      y: 780,
      menuWidth: 236,
      menuHeight: 260,
      ...VIEW,
    });
    expect(pos.top + 260).toBeLessThanOrEqual(800);
  });

  it('keeps the padding floor when the menu is taller than the viewport', () => {
    const pos = chartContextMenuPosition({
      x: 5,
      y: 5,
      menuWidth: 236,
      menuHeight: 2000,
      ...VIEW,
    });
    expect(pos).toEqual({ top: 8, left: 8 });
  });
});

describe('chartSubmenuPosition', () => {
  it('opens to the right of the parent menu', () => {
    expect(
      chartSubmenuPosition({
        parentLeft: 200,
        parentWidth: 236,
        rowTop: 300,
        submenuWidth: 190,
        submenuHeight: 180,
        ...VIEW,
      }),
    ).toEqual({ top: 300, left: 436 });
  });

  it('flips to the left when the right side would overflow', () => {
    const pos = chartSubmenuPosition({
      parentLeft: 700,
      parentWidth: 236,
      rowTop: 300,
      submenuWidth: 190,
      submenuHeight: 180,
      ...VIEW,
    });
    expect(pos.left).toBe(510);
  });
});
