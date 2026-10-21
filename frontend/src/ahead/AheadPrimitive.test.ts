import type { Logical } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { paneWords, publishPaneWords } from '../chart';
import { AHEAD_WORDS_SOURCE, AheadPrimitive, edgeInset } from './AheadPrimitive';
import { AHEAD_DRAW, CHIP_H, crosses, overlaps, type Rect, type Seg } from './aheadCanvas';
import { freeSpot } from './AheadZoneRenderer';
import { ANCHOR_T, X, Y, fakeChart, paint, sampleScene } from './aheadTestKit';

function attach(scene = sampleScene(), opts: Parameters<typeof fakeChart>[0] = {}) {
  const f = fakeChart(opts);
  const p = new AheadPrimitive();
  p.attached(f.param);
  p.setScene(scene);
  p.updateAllViews();
  const [under, over] = p.paneViews();
  return { ...f, p, under, over };
}

const nextMicrotask = () => new Promise<void>(resolve => queueMicrotask(resolve));

describe('AheadPrimitive', () => {
  it('puts step k at logicalToCoordinate(index of the anchor + k), the zone right of the anchor candle', () => {
    const { p } = attach();
    const px = p.px;
    expect(px).not.toBeNull();
    expect(px?.anchor).toEqual({ x: X(9), y: Y(5) });
    for (const k of [1, 7, 15]) expect(px?.xs.get(k)).toBe(X(9 + k));
    expect(px?.left).toBe(X(9) + 5);
    // The zone ends just past the last step's ghost bar (half a step at 62%, plus a pixel).
    expect(px?.right).toBeCloseTo(X(9 + 15) + 5 * 0.62 + 1);
    expect(p.stepX(2.5)).toBe(X(11.5));
  });

  it('places a fractional step between its whole neighbours, as lightweight-charts places whole indexes only', () => {
    // The real time scale answers 0 (the pane's left edge) for a fractional index: the meet must not land there.
    const { p, over } = attach(sampleScene({ meet: { steps: 7.4, p: 4.98, text: 'lines meet ≈ 09:17', inZone: true },
      lines: [
        { kind: 'support', fromP: 4.9, slope: 0.01, toSteps: 7.4, color: '#34d399' },
        { kind: 'resistance', fromP: 5.1, slope: -0.015, toSteps: 7.4, color: '#ff9f43' },
      ] }), { wholeOnly: true });
    expect(p.stepX(7.4)).toBeCloseTo(X(16.4));
    expect(p.stepX(7)).toBe(X(16));
    const ctx = paint(over.renderer() as never);
    expect(ctx.arc.mock.calls[0][0]).toBeCloseTo(X(16.4));
    // Both dotted lines run forward from the anchor candle to the meet, never back to the pane's left edge.
    const ends = ctx.lineTo.mock.calls.slice(0, 2).map(c => c[0] as number);
    for (const x of ends) expect(x).toBeCloseTo(X(16.4));
    expect(ctx.lineTo.mock.calls.some(c => c[0] === 0)).toBe(false);
  });

  it('hatches the zone, draws the fan from the anchor candle and the paths, under the candles', () => {
    const { under } = attach();
    expect(under.zOrder?.()).toBe('bottom');
    const ctx = paint(under.renderer() as never);
    expect(ctx.fillRect).toHaveBeenCalledWith(X(9) + 5, 0, X(24) + 4.1 - (X(9) + 5), 400);
    // Two bands, each starting at the anchor candle's close.
    expect(ctx.fill).toHaveBeenCalledTimes(2);
    expect(ctx.moveTo).toHaveBeenCalledWith(X(9), Y(5));
    expect(ctx.lineTo).toHaveBeenCalledWith(X(10), Y(5.02));
  });

  it('runs the zone its full 15 steps, the word column at the edge or not (the framing leaves it room)', () => {
    const { chart, under } = attach();
    // Words away from the edge do not count; the column at the edge does.
    publishPaneWords(chart, 'stock-read', [{ left: 340, top: 10, right: 587, bottom: 24 }, { left: 10, top: 0,
      right: 60, bottom: 14 }]);
    expect(edgeInset(chart, 600)).toBe(260);
    const ctx = paint(under.renderer() as never);
    expect(ctx.rect).toHaveBeenCalledWith(0, 0, X(24) + 4.1, 400);
    // The column never takes more than 45% of the pane.
    publishPaneWords(chart, 'stock-read', [{ left: 100, top: 10, right: 587, bottom: 24 }]);
    expect(edgeInset(chart, 600)).toBe(270);
    publishPaneWords(chart, 'stock-read', []);
    expect(edgeInset(chart, 600)).toBe(0);
  });

  it('draws the lines to the meet, the ring, the stubs and the chips; the minute labels go on the time axis', () => {
    const { p, over, chart } = attach(sampleScene(), { spacing: 30 });
    expect(over.zOrder?.()).toBe('top');
    const ctx = paint(over.renderer() as never, 900, 400);
    const texts = ctx.fillText.mock.calls.map(c => c[0]);
    expect(texts).toEqual(expect.arrayContaining(['lines meet ≈ 09:18', '▲ 5.20 first · 27% (forecast)',
      'neither in 15 min · 30% (forecast)']));
    // "now HH:MM" is the heading's (DOM, on a backdrop): a level line drawn on the pane never crosses it.
    expect(texts).not.toContain('now 09:10');
    // Nothing writes minute labels over the ghost volume at the pane's bottom: they are the time axis's.
    expect(texts).not.toContain('09:15');
    const axis = p.timeAxisViews();
    expect(axis.map(v => v.text())).toEqual(['09:15', '09:20', '09:25']);
    expect(axis.map(v => v.coordinate())).toEqual([100 + 14 * 30, 100 + 19 * 30, 100 + 24 * 30]);
    expect(ctx.arc).toHaveBeenCalledWith(100 + 17 * 30, Y(4.98), 6, 0, Math.PI * 2);
    expect(ctx.setLineDash).toHaveBeenCalledWith([2, 5]);
    expect(paneWords(chart).rects.length).toBeGreaterThan(0);
  });

  it("puts the meet's words over its ring and over the lines running into it, and no odds chip on a line", () => {
    // The odds chip "neither" sits at the meet's price, right where the support line runs.
    const scene = sampleScene({ chips: [{ p: 4.98, text: 'neither in 15 min · 30% (forecast)', short: 'neither 30%',
      color: '#8b92a5' }] });
    const { p, over } = attach(scene, { spacing: 30 });
    const ctx = paint(over.renderer() as never, 900, 400);
    const rectOf = (text: string): Rect => {
      const call = ctx.fillText.mock.calls.find(c => c[0] === text) as [string, number, number];
      const left = call[1] - 6;
      const y = call[2] - 0.5;
      return { left, right: left + text.length * 6 + 12, top: y - 9, bottom: y + 9 };
    };
    const a = p.px!.anchor;
    const segs: Seg[] = scene.lines.map(l => ({
      a: { x: a.x, y: Y(l.fromP) },
      b: { x: p.stepX(l.toSteps)!, y: Y(l.fromP + l.slope * l.toSteps) },
    }));
    const meet = rectOf('lines meet ≈ 09:18');
    expect(meet.bottom).toBeLessThan(Y(4.98) - 6);
    for (const g of segs) expect(crosses(g, meet, 0)).toBe(false);
    const neither = rectOf('neither in 15 min · 30% (forecast)');
    for (const g of segs) expect(crosses(g, neither, 0)).toBe(false);
  });

  it('keeps chips that would sit on each other apart', () => {
    const { over } = attach();
    const ctx = paint(over.renderer() as never);
    const ys = ctx.fillText.mock.calls.filter(c => String(c[0]).includes('%')).map(c => c[2] as number);
    expect(ys).toHaveLength(2);
    expect(Math.abs(ys[0] - ys[1])).toBeGreaterThanOrEqual(18);
  });

  it('tells the heading where the zone went, once per move of a pixel or more', () => {
    const { p, over } = attach();
    const cb = vi.fn();
    p.setLayoutListener(cb);
    cb.mockClear();
    paint(over.renderer() as never);
    expect(cb).toHaveBeenCalledWith({ left: X(9) + 5, right: X(24) + 4.1, top: 0, capRight: X(24) + 4.1 });
    paint(over.renderer() as never);
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("ends the heading short of the stock read's words over the zone's top, so its backdrop hides none", () => {
    const { p, over, chart } = attach();
    const cb = vi.fn();
    p.setLayoutListener(cb);
    // A level's label starting inside the zone near its top; another lower down does not count.
    publishPaneWords(chart, 'stock-read', [{ left: 220, top: 20, right: 380, bottom: 34 },
      { left: 200, top: 200, right: 380, bottom: 214 }]);
    paint(over.renderer() as never);
    expect(cb).toHaveBeenLastCalledWith(expect.objectContaining({ capRight: 220 }));
    publishPaneWords(chart, 'stock-read', []);
  });

  it('keeps on the price scale only what it draws, and only once the zone is in view', () => {
    const { p, over } = attach();
    // Before the zone has been drawn there is nothing on screen to keep in view.
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
    paint(over.renderer() as never);
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toEqual({ priceRange: { minValue: 4.75, maxValue: 5.25 } });
    expect(p.autoscaleInfo(0 as Logical, 5 as Logical)).toBeNull();
    p.setScene(sampleScene({ keepInView: null }));
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
    p.setScene(sampleScene({ on: false }));
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
  });

  it('stretches no price scale for a zone off the pane', () => {
    const { p, over } = attach();
    paint(over.renderer() as never);
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).not.toBeNull();
    // A pane narrower than the anchor candle's x: the zone is off screen.
    paint(over.renderer() as never, 150, 400);
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
  });

  it('never draws a chip left of the zone, over real candles: a narrow zone gets the odds-only words', () => {
    const { p, over } = attach();
    const ctx = paint(over.renderer() as never);
    const left = (p.px?.left ?? 0);
    const texts = ctx.fillText.mock.calls.map(c => c[0]);
    expect(texts).toEqual(expect.arrayContaining(['▲ 27%', 'neither 30%']));
    expect(texts).not.toContain('▲ 5.20 first · 27% (forecast)');
    for (const call of ctx.roundRect.mock.calls) expect(call[0] as number).toBeGreaterThanOrEqual(left);
    // A zone too narrow even for the short words draws no chip at all.
    const tiny = paint(over.renderer() as never, X(9) + 5 + 30, 400);
    expect(tiny.fillText.mock.calls.map(c => c[0]).filter(t => String(t).includes('%'))).toEqual([]);
  });

  it("does not count its own chips as the word column (no repaint loop)", async () => {
    const { chart, over, requestUpdate } = attach();
    paint(over.renderer() as never);
    // Ahead's chips sit at the zone's right edge, inside the column's slack: they must not move its own clip.
    publishPaneWords(chart, AHEAD_WORDS_SOURCE, [{ left: 500, top: 10, right: 596, bottom: 24 }]);
    expect(edgeInset(chart, 600)).toBe(0);
    paint(over.renderer() as never);
    await nextMicrotask();
    requestUpdate.mockClear();
    paint(over.renderer() as never);
    await nextMicrotask();
    expect(requestUpdate).not.toHaveBeenCalled();
  });

  it('draws nothing, and takes its words back, with Ahead off or no anchor on the pane', async () => {
    const { p, over, chart } = attach();
    paint(over.renderer() as never);
    p.setScene(sampleScene({ on: false }));
    p.updateAllViews();
    expect(p.px).toBeNull();
    const ctx = paint(over.renderer() as never);
    expect(ctx.fillText).not.toHaveBeenCalled();
    await nextMicrotask();
    p.setScene(sampleScene({ anchorT: ANCHOR_T + 3600 }));
    p.updateAllViews();
    expect(p.px).toBeNull();
    p.detached();
    expect(paneWords(chart).rects).toEqual([]);
  });

  it('never adds anything to the series', () => {
    const { series, over, under } = attach();
    paint(under.renderer() as never);
    paint(over.renderer() as never);
    expect(series.setData).not.toHaveBeenCalled();
    expect(series.update).not.toHaveBeenCalled();
  });

  it('keeps the fan and the paths above the volume band, a caret where a path leaves the price area', () => {
    // The volume overlay's band starts 80% down the 400 px pane: y 320. One path runs down to 3.8 (y 340).
    const deep = Array.from({ length: 15 }, (_, i) => (i < 5 ? 5.02 : 3.8));
    const scene = sampleScene({ paths: [{ points: deep, color: '#c7d2fe', alpha: 0.34 }] });
    const { p, under, series } = attach(scene);
    p.setVolumeSeries(series as never);
    p.updateAllViews();
    expect(p.px?.priceBottom).toBe(320);
    const ctx = paint(under.renderer() as never);
    expect(ctx.rect).toHaveBeenCalledWith(0, 0, X(24) + 4.1, 320);
    // The hatch still runs the pane's full height (the ghost volume sits in it).
    expect(ctx.fillRect).toHaveBeenCalledWith(X(9) + 5, 0, X(24) + 4.1 - (X(9) + 5), 400);
    // The caret: a small "v" on the band's top edge at the first step under it (step 6).
    expect(ctx.moveTo).toHaveBeenCalledWith(X(15) - 3, 316);
    expect(ctx.lineTo).toHaveBeenCalledWith(X(15), 319);
    // Without a volume band the price area is the whole pane, and no caret.
    p.setVolumeSeries(null);
    p.updateAllViews();
    expect(p.px?.priceBottom).toBeNull();
    const plain = paint(under.renderer() as never);
    expect(plain.lineTo).not.toHaveBeenCalledWith(X(15), 319);
  });

  it("gives a wall chip its 'if it breaks' line only when the zone is wide enough for it", () => {
    const scene = sampleScene({ chips: [{ p: 5.2, text: '▲ 5.20 first · 27% (forecast)', short: '▲ 27%',
      color: '#f0876f', sub: 'breaks 38% · then 45% reach 5.40 · 40% back under' }] });
    const wide = attach(scene, { spacing: 30 });
    const texts = paint(wide.over.renderer() as never, 900, 400).fillText.mock.calls.map(c => c[0]);
    expect(texts).toEqual(expect.arrayContaining(['▲ 5.20 first · 27% (forecast)', 'breaks 38% · then 45% reach 5.40 · 40% back under']));
    // A narrow zone: the odds-only chip, and the card carries the break.
    const narrow = attach(scene);
    const few = paint(narrow.over.renderer() as never).fillText.mock.calls.map(c => c[0]);
    expect(few).toContain('▲ 27%');
    expect(few).not.toContain('breaks 38% · then 45% reach 5.40 · 40% back under');
  });

  it("never moves a wall chip for its 'if it breaks' line: the line goes over it, or is left to the card", () => {
    const text = '▲ 5.05 first · 27% (forecast)';
    const sub = 'breaks 38% · then 45% reach 5.40 · 40% back under';
    const flat = (p: number) => ({ kind: 'resistance' as const, fromP: p, slope: 0, toSteps: 15, color: '#ff9f43' });
    // A line runs just under the chip (y 108 for a chip at 90): the second line cannot go under it.
    const scene = (lines: ReturnType<typeof flat>[]) => sampleScene({ lines, meet: null, hLines: [],
      chips: [{ p: 5.05, text, short: '▲ 27%', color: '#f0876f', sub }] });
    const yOf = (ctx: ReturnType<typeof paint>, t: string) => {
      const call = ctx.fillText.mock.calls.find(c => c[0] === t);
      return call ? (call[2] as number) - 0.5 : null;
    };
    const under = attach(scene([flat(4.96)]), { spacing: 30 });
    const one = paint(under.over.renderer() as never, 900, 400);
    expect(yOf(one, text)).toBe(Y(5.05));
    expect(yOf(one, sub)).toBe(Y(5.05) - 18);
    // A line over it too: no room either side, so the chip stays on its wall and the card carries the break.
    const both = attach(scene([flat(4.96), flat(5.14)]), { spacing: 30 });
    const two = paint(both.over.renderer() as never, 900, 400);
    expect(yOf(two, text)).toBe(Y(5.05));
    expect(yOf(two, sub)).toBeNull();
  });

  it("places the walls' chips first, on their walls; 'neither' yields, in the free space between them", () => {
    const above = '▲ 5.30 first · 30% (forecast)';
    const below = '▼ 4.90 first · 60% (forecast)';
    const neither = 'neither in 15 min · 10% (forecast)';
    // "Neither" asks for a price just over the wall below: placed first it would push that wall's chip off its wall.
    const scene = (neitherP: number, belowP = 4.9, aboveP = 5.3) => sampleScene({ lines: [], meet: null, hLines: [],
      chips: [
        { p: aboveP, text: above, short: '▲ 30%', color: '#f0876f', role: 'wall' },
        { p: neitherP, text: neither, short: 'neither 10%', color: '#8b92a5', role: 'neither' },
        { p: belowP, text: below, short: '▼ 60%', color: '#2dd4bf', role: 'wall' },
      ] });
    const yOf = (ctx: ReturnType<typeof paint>, t: string) => {
      const call = ctx.fillText.mock.calls.find(c => c[0] === t);
      return call ? (call[2] as number) - 0.5 : null;
    };
    const { over } = attach(scene(4.95), { spacing: 30 });
    const ctx = paint(over.renderer() as never, 900, 400);
    expect(yOf(ctx, above)).toBe(Y(5.3));
    expect(yOf(ctx, below)).toBe(Y(4.9));
    const ny = yOf(ctx, neither) as number;
    expect(ny).toBeGreaterThan(Y(5.3));
    expect(ny).toBeLessThan(Y(4.9));
    const box = (y: number): Rect => ({ left: 0, right: 1, top: y - CHIP_H / 2, bottom: y + CHIP_H / 2 });
    expect(overlaps(box(ny), box(Y(4.9)), 0)).toBe(false);
    // No free space between walls this close: "neither" is left to the panel's card, the walls keep their chips.
    const tight = attach(scene(4.94, 4.88, 5), { spacing: 30 });
    const t = paint(tight.over.renderer() as never, 900, 400);
    expect(yOf(t, neither)).toBeNull();
    expect(yOf(t, 'neither 10%')).toBeNull();
    expect(yOf(t, below)).toBe(Y(4.88));
    expect(yOf(t, above)).toBe(Y(5));
  });

  it('finds the free spot nearest the middle asked for, inside the space, or none', () => {
    const free = (lo: number, hi: number) => (cy: number) => cy + CHIP_H / 2 <= lo || cy - CHIP_H / 2 >= hi;
    expect(freeSpot(100, 0, 400, () => true)).toBe(100);
    // Something on 90-130: the nearest centre clear of it, outward from 100.
    expect(freeSpot(100, 0, 400, free(90, 130))).toBe(80);
    // Wanted past the space's edge: it starts at the edge.
    expect(freeSpot(10, 50, 400, () => true)).toBe(50 + CHIP_H / 2);
    expect(freeSpot(100, 90, 100, () => true)).toBeNull();
    expect(freeSpot(100, 60, 140, () => false)).toBeNull();
  });

  it('dims the fan on a strategy scope', () => {
    const fillAlphas = (dim: boolean) => {
      const { p, under } = attach();
      p.setScene(sampleScene(), dim);
      p.updateAllViews();
      const seen: number[] = [];
      paint(under.renderer() as never, 600, 400, ctx => ctx.fill.mockImplementation(() => seen.push(ctx.globalAlpha)));
      return seen;
    };
    expect(fillAlphas(false)).toEqual([AHEAD_DRAW.fanOuter, AHEAD_DRAW.fanInner]);
    expect(fillAlphas(true)).toEqual([AHEAD_DRAW.fanOuter * AHEAD_DRAW.fanDim, AHEAD_DRAW.fanInner * AHEAD_DRAW.fanDim]);
    expect(AHEAD_WORDS_SOURCE).toBe('ahead');
  });
});
