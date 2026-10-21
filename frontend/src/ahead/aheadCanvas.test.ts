import { describe, expect, it } from 'vitest';
import { chip, crosses, hatch, overlaps, topOver } from './aheadCanvas';
import { fakeCtx } from './aheadTestKit';

const ctx = () => fakeCtx() as unknown as CanvasRenderingContext2D & ReturnType<typeof fakeCtx>;

describe('aheadCanvas', () => {
  it('hatches inside the rectangle only, with stripes fixed to the pane', () => {
    const c = ctx();
    hatch(c, { left: 100, top: 0, right: 200, bottom: 50 }, '#1b2030', 'rgba(255,255,255,0.045)');
    expect(c.fillRect).toHaveBeenCalledWith(100, 0, 100, 50);
    expect(c.rect).toHaveBeenCalledWith(100, 0, 100, 50);
    expect(c.clip).toHaveBeenCalled();
    const starts = c.moveTo.mock.calls.map(m => m[0] as number);
    const step = 9 * Math.SQRT2;
    for (const x of starts) expect(Math.abs(x / step - Math.round(x / step))).toBeLessThan(1e-9);
  });

  it('draws nothing for an empty zone', () => {
    const c = ctx();
    hatch(c, { left: 100, top: 0, right: 100, bottom: 50 }, '#000', '#fff');
    expect(c.fillRect).not.toHaveBeenCalled();
  });

  it('puts a chip at its anchor and leaves out one that would not fit', () => {
    const c = ctx();
    const r = chip(c, 300, 50, 'abc', '#fff', '#000', 'end', { width: 400, height: 100 });
    expect(r).toEqual({ left: 300 - 30, top: 41, right: 300, bottom: 59 });
    expect(c.fillText).toHaveBeenCalledWith('abc', 276, 50.5);
    expect(chip(c, 10, 50, 'abc', '#fff', '#000', 'end', { width: 400, height: 100 })).toBeNull();
    expect(chip(c, 300, 95, 'abc', '#fff', '#000', 'end', { width: 400, height: 100 })).toBeNull();
  });

  it('tells overlapping rectangles apart from ones with room between', () => {
    const a = { left: 0, top: 0, right: 10, bottom: 10 };
    expect(overlaps(a, { left: 11, top: 0, right: 20, bottom: 10 })).toBe(true);
    expect(overlaps(a, { left: 13, top: 0, right: 20, bottom: 10 })).toBe(false);
  });

  it("tells a chip on a line from one clear of it, and a line's highest point over some columns", () => {
    const seg = { a: { x: 0, y: 100 }, b: { x: 100, y: 0 } };
    expect(crosses(seg, { left: 40, right: 60, top: 45, bottom: 55 })).toBe(true);
    expect(crosses(seg, { left: 40, right: 60, top: 70, bottom: 80 })).toBe(false);
    expect(crosses(seg, { left: 120, right: 140, top: 0, bottom: 100 })).toBe(false);
    expect(topOver([seg], 20, 50)).toBe(50);
    expect(topOver([seg], 150, 160)).toBe(Infinity);
  });
});
