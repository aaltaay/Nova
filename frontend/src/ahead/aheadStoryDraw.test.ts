import { describe, expect, it } from 'vitest';
import { AheadPrimitive } from './AheadPrimitive';
import { CHIP_H, overlaps, type Rect } from './aheadCanvas';
import { AHEAD_COLORS, AHEAD_STORY_ALPHA, AHEAD_STORY_GLYPH } from './aheadConstants';
import type { AheadScene, SceneStory } from './aheadSceneTypes';
import { ptAt, stretch } from './aheadStoryDraw';
import { X, Y, fakeChart, paint, sampleScene, type FakeCtx } from './aheadTestKit';

function draw(over: Partial<AheadScene>, layer: 0 | 1 = 0, width = 600, spacing?: number) {
  const f = fakeChart(spacing ? { spacing } : {});
  const p = new AheadPrimitive();
  p.attached(f.param);
  p.setScene(sampleScene({ fan: null, lines: [], meet: null, hLines: [], chips: [], ...over }));
  p.updateAllViews();
  const strokes: { alpha: number; color: string; width: number }[] = [];
  const ctx = paint(p.paneViews()[layer].renderer() as never, width, 400, (c: FakeCtx) => {
    c.stroke.mockImplementation(() => strokes.push({ alpha: c.globalAlpha, color: c.strokeStyle, width: c.lineWidth }));
  });
  return { ctx, strokes, p };
}

// Nova Marketing Sample Data: made-up closes; the anchor candle closes at 5 (aheadTestKit).
const POINTS = [5.04, 5.1, 5.14, 5.2, 5.24, 5.2, 5.18, 5.16, 5.15, 5.14, 5.13, 5.12, 5.11, 5.1, 5.1];
const TRADE: SceneStory = {
  start: 5,
  points: POINTS,
  segments: [
    { from: 0, to: 1.5, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before },
    { from: 1.5, to: 3.5, color: AHEAD_COLORS.target, alpha: AHEAD_STORY_ALPHA.during },
    { from: 3.5, to: 15, color: AHEAD_COLORS.target, alpha: AHEAD_STORY_ALPHA.after },
  ],
  marks: [
    { k: 1.5, p: 5.07, kind: 'fill', color: AHEAD_COLORS.trigger },
    { k: 3.5, p: 5.17, kind: 'target', color: AHEAD_COLORS.target },
  ],
  label: '✓ target first · 60% of fills (forecast)',
  short: '✓ target first · 60% of fills',
  tiny: '✓ 60% of fills',
  color: AHEAD_COLORS.target,
};

describe('the soft cloud', () => {
  it('draws every path, one faint stroke each, with no outcome colour', () => {
    const cloud = Array.from({ length: 200 }, (_, j) => POINTS.map((p) => p + j * 0.0001));
    const { strokes } = draw({ cloud, story: [] });
    const faint = strokes.filter((s) => s.alpha === AHEAD_STORY_ALPHA.cloud);
    expect(faint).toHaveLength(200);
    expect(new Set(faint.map((s) => s.color))).toEqual(new Set([AHEAD_COLORS.path]));
  });
});

describe('a story path', () => {
  it('is drawn stage by stage: grey before the fill, coloured to the exit, faded after', () => {
    const { strokes } = draw({ cloud: [], story: [TRADE] });
    const story = strokes.filter((s) => s.width === 1.6 && s.alpha !== 1);
    expect(story.map((s) => [s.color, s.alpha])).toEqual([
      [AHEAD_COLORS.muted, AHEAD_STORY_ALPHA.before],
      [AHEAD_COLORS.target, AHEAD_STORY_ALPHA.during],
      [AHEAD_COLORS.target, AHEAD_STORY_ALPHA.after],
    ]);
  });

  it('places a fractional crossing on the line between its two whole steps', () => {
    const pts = [{ x: 0, y: 100 }, { x: 10, y: 80 }, { x: 20, y: 60 }, { x: 30, y: 70 }];
    expect(ptAt(pts, 1.5)).toEqual({ x: 15, y: 70 });
    expect(ptAt(pts, 0)).toEqual({ x: 0, y: 100 });
    expect(ptAt(pts, 3)).toEqual({ x: 30, y: 70 });
    // A stretch starts and ends on its crossings, with the whole steps between.
    expect(stretch(pts, 0.5, 2.25)).toEqual([{ x: 5, y: 90 }, { x: 10, y: 80 }, { x: 20, y: 60 }, { x: 22.5, y: 62.5 }]);
    expect(ptAt([pts[0], null], 0.5)).toBeNull();
    // On the pane: the coloured stretch starts half way between steps 1 and 2.
    const { ctx } = draw({ cloud: [], story: [TRADE] });
    const at = { x: X(10.5), y: (Y(5.04) + Y(5.1)) / 2 };
    expect(ctx.moveTo.mock.calls.some(([x, y]) => Math.abs(x - at.x) < 1e-6 && Math.abs(y - at.y) < 1e-6)).toBe(true);
  });

  it('marks the fill with a dot, a target with ✓, a stop with ✕ and a wall with a filled diamond, on the line', () => {
    const stop: SceneStory = { ...TRADE, marks: [{ k: 2, p: 5.1, kind: 'stop', color: AHEAD_COLORS.stop }] };
    const wall: SceneStory = { ...TRADE, marks: [{ k: 4, p: 5.2, kind: 'wall', color: AHEAD_COLORS.wallAbove }] };
    const { ctx } = draw({ cloud: [], story: [TRADE, stop, wall] }, 1);
    const fill = { x: X(10.5), y: (Y(5.04) + Y(5.1)) / 2 };
    const arcs = ctx.arc.mock.calls;
    expect(arcs.some(([x, y, r]) => Math.abs(x - fill.x) < 1e-6 && Math.abs(y - fill.y) < 1e-6 && r === 3.2)).toBe(true);
    // The wall touch: a filled diamond in the wall's colour (never a ring, which is the meet's).
    expect(arcs.some(([x, y]) => x === X(13) && y === Y(5.2))).toBe(false);
    expect(ctx.moveTo).toHaveBeenCalledWith(X(13), Y(5.2) - 4.5);
    expect(ctx.lineTo).toHaveBeenCalledWith(X(13) + 4.5, Y(5.2));
    expect(ctx.lineTo).toHaveBeenCalledWith(X(13), Y(5.2) + 4.5);
    const glyphs = ctx.fillText.mock.calls.map((c) => [c[0], c[1], c[2]]);
    expect(glyphs).toContainEqual([AHEAD_STORY_GLYPH.target, X(12.5), (Y(5.14) + Y(5.2)) / 2]);
    expect(glyphs).toContainEqual([AHEAD_STORY_GLYPH.stop, X(11), Y(5.1)]);
    // Marks are drawn over the zone (its top layer), never under the candles with the lines.
    const under = draw({ cloud: [], story: [TRADE, stop, wall] }, 0).ctx;
    expect(under.fillText).not.toHaveBeenCalled();
    expect(under.arc).not.toHaveBeenCalled();
  });

  it("starts at the price its crossings were counted from, so a step-0 crossing sits on the line and the level", () => {
    // The answer's price (4.98) is under the anchor candle's close (5): the buy stop at 5.01 is crossed half way to
    // the first close (5.04). The line starts at 4.98, and the fill dot sits on it at 5.01 -- not at 5.02, where the
    // line from the candle's close would cross step 0.5.
    const early: SceneStory = { ...TRADE, start: 4.98,
      segments: [{ from: 0, to: 0.5, color: AHEAD_COLORS.muted, alpha: AHEAD_STORY_ALPHA.before },
        { from: 0.5, to: 15, color: AHEAD_COLORS.target, alpha: AHEAD_STORY_ALPHA.during }],
      marks: [{ k: 0.5, p: 5.01, kind: 'fill', color: AHEAD_COLORS.trigger }] };
    const under = draw({ cloud: [], story: [early] }, 0).ctx;
    expect(under.moveTo).toHaveBeenCalledWith(X(9), Y(4.98));
    const { ctx } = draw({ cloud: [], story: [early] }, 1);
    const dots = ctx.arc.mock.calls.filter(([, , r]) => r === 3.2);
    expect(dots).toHaveLength(1);
    expect(dots[0][0]).toBeCloseTo(X(9.5));
    expect(dots[0][1]).toBeCloseTo(Y(5.01));
  });
});

describe("a story path's end label", () => {
  const yOf = (ctx: FakeCtx, t: string) => {
    const call = ctx.fillText.mock.calls.find((c) => c[0] === t);
    return call ? (call[2] as number) - 0.5 : null;
  };

  it("yields to a wall's chip at the same price, keeping its words inside the zone", () => {
    const chips: AheadScene['chips'] = [
      { p: 5.1, text: TRADE.label, short: TRADE.short, color: TRADE.color, role: 'story' },
      { p: 5.1, text: '▲ 5.10 first · 27% (forecast)', short: '▲ 27%', color: AHEAD_COLORS.wallAbove, role: 'wall' },
    ];
    const { ctx, p } = draw({ cloud: [], story: [TRADE], chips }, 1, 900, 30);
    expect(yOf(ctx, '▲ 5.10 first · 27% (forecast)')).toBe(Y(5.1));
    const end = yOf(ctx, TRADE.label) as number;
    expect(end).not.toBeNull();
    const box = (y: number): Rect => ({ left: 0, right: 1, top: y - CHIP_H / 2, bottom: y + CHIP_H / 2 });
    expect(overlaps(box(end), box(Y(5.1)), 0)).toBe(false);
    for (const call of ctx.roundRect.mock.calls) expect(call[0] as number).toBeGreaterThanOrEqual(p.px?.left ?? 0);
  });

  it('yields to the "neither" odds chip: a case ending between the walls never pushes it off the chart', () => {
    // Walls at 5.30 (y 40) and 5.00 (y 100): between their chips there is room for one chip only, at y 69-71. The
    // middle case ends right there (5.15, y 70), where "neither" asks to be.
    const neither = 'neither in 15 min · 30% (forecast)';
    const middle: SceneStory = { ...TRADE, label: 'middle case', short: 'middle', color: AHEAD_COLORS.muted,
      marks: [] };
    const chips: AheadScene['chips'] = [
      { p: 5.3, text: '▲ 5.30 first · 20% (forecast)', short: '▲ 20%', color: AHEAD_COLORS.wallAbove, role: 'wall' },
      { p: 5.15, text: neither, short: 'neither 30%', color: AHEAD_COLORS.muted, role: 'neither' },
      { p: 5, text: '▼ 5.00 first · 50% (forecast)', short: '▼ 50%', color: AHEAD_COLORS.wallBelow, role: 'wall' },
      { p: 5.15, text: middle.label, short: middle.short, color: middle.color, role: 'story' },
    ];
    const { ctx } = draw({ cloud: [], story: [middle], chips }, 1, 900, 30);
    const ny = yOf(ctx, neither) as number;
    expect(ny).toBe(Y(5.15));
    const end = yOf(ctx, 'middle case') as number;
    expect(end).not.toBeNull();
    const box = (y: number): Rect => ({ left: 0, right: 1, top: y - CHIP_H / 2, bottom: y + CHIP_H / 2 });
    for (const y of [ny, Y(5.3), Y(5)]) expect(overlaps(box(end), box(y), 0)).toBe(false);
  });

  it('drops "(forecast)" in a narrower zone and keeps the odds only in a narrow one, always saying "of fills"', () => {
    const chips: AheadScene['chips'] = [{ p: 5.1, text: TRADE.label, short: TRADE.short, tiny: TRADE.tiny,
      color: TRADE.color, role: 'story', story: 0 }];
    const texts = (width: number, spacing?: number) => draw({ cloud: [], story: [TRADE], chips }, 1, width, spacing)
      .ctx.fillText.mock.calls.map((c) => c[0]);
    // A wide zone (445 px): the full words; 228 px: without "(forecast)"; 149 px: the odds only.
    expect(texts(900, 30)).toContain('✓ target first · 60% of fills (forecast)');
    const mid = texts(613, 30);
    expect(mid).toContain('✓ target first · 60% of fills');
    expect(mid).not.toContain(TRADE.label);
    const narrow = texts(600);
    expect(narrow).toContain('✓ 60% of fills');
    expect(narrow).not.toContain(TRADE.short);
  });
});
