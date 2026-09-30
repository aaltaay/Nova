/**
 * The export page's math (ADR 039): a crop fitted without stretching, blur
 * boxes carried through the fit, the frame times of a piece, and a window
 * capture's crop from the frame's own size -- pinned to what was measured on
 * the desk's monitors on 2026-09-29 (a marker at the page's top-left corner
 * landed at y = 26 in a 784 x 460 frame at 100%, and y = 40 in 1178 x 694 at 150%).
 */
import { describe, expect, it } from 'vitest';
import { fitRect, frameTimes, mapBox, windowCrop } from './exportDraw';

describe('fitRect / mapBox', () => {
  it('fits a crop without stretching and carries a box through the fit', () => {
    const fit = fitRect({ x: 0, y: 0, w: 1000, h: 500 }, 1200, 700);
    expect(fit).toEqual({ x: 0, y: 50, w: 1200, h: 600, scale: 1.2 });
    expect(mapBox({ x: 100, y: 100, w: 50, h: 25 }, fit)).toEqual({ x: 120, y: 170, w: 60, h: 30 });
  });
});

describe('frameTimes', () => {
  it('steps at the output rate and always gives one frame', () => {
    expect(frameTimes(10, 11, 4)).toEqual([10, 10.25, 10.5, 10.75]);
    expect(frameTimes(10, 10.01, 30)).toEqual([10]);
  });
});

describe('windowCrop', () => {
  it('finds the page under the title bar at 100%', () => {
    const r = windowCrop({ dip: { x: 0, y: 0, w: 24, h: 24 }, content: { width: 784, height: 435 }, blur: [] }, 784, 460);
    expect(r?.crop).toEqual({ x: 0, y: 26, w: 24, h: 24 });
  });

  it('finds it at 150% within a pixel of the measured marker', () => {
    const r = windowCrop({ dip: { x: 0, y: 0, w: 24, h: 24 }, content: { width: 786, height: 438 }, blur: [] }, 1178, 694);
    expect(Math.abs((r?.crop.y ?? 0) - 40)).toBeLessThanOrEqual(1);
    expect(r?.crop.x).toBe(0);
  });

  it('gives the whole frame for the window picture, and blur boxes inside the crop', () => {
    expect(windowCrop({ dip: null, content: { width: 784, height: 435 }, blur: [] }, 784, 460)?.crop).toEqual({ x: 0, y: 0, w: 784, h: 460 });
    const r = windowCrop({ dip: { x: 100, y: 100, w: 400, h: 200 }, content: { width: 784, height: 435 }, blur: [{ x: 350, y: 150, w: 300, h: 100 }] }, 784, 460);
    expect(r?.crop).toEqual({ x: 100, y: 126, w: 400, h: 200 });
    expect(r?.blur).toEqual([{ x: 250, y: 50, w: 150, h: 100 }]);
  });

  it('follows a resized window: the crop is worked out from each frame', () => {
    const spec = { dip: { x: 0, y: 40, w: 984, h: 595 }, content: { width: 984, height: 635 }, blur: [] };
    expect(windowCrop(spec, 984, 660)?.crop).toEqual({ x: 0, y: 66, w: 984, h: 594 });
    expect(windowCrop(spec, 492, 330)?.crop).toEqual({ x: 0, y: 33, w: 492, h: 297 });
  });
});
