/** Where the zone's chips go, and the order they are drawn in (ADR 065): a chip never hides a story path, never sits
 * on a mark, and a wall's "if it breaks" line stays compact. Nova Marketing Sample Data: made-up prices. */
import { describe, expect, it } from 'vitest';
import { AheadPrimitive } from './AheadPrimitive';
import { CHIP_H, crosses, nearestOn, overlaps, type Rect } from './aheadCanvas';
import { AHEAD_COLORS, AHEAD_STORY_ALPHA } from './aheadConstants';
import type { AheadScene, SceneStory, StoryMark } from './aheadSceneTypes';
import { SUB_MAX_SHARE } from './aheadZoneChips';
import { Y, fakeChart, paint, sampleScene, type FakeCtx } from './aheadTestKit';

/** Paint the zone's top layer at 30 px a step on a 900 x 400 pane (or `width`). */
function over(scene: Partial<AheadScene>, width = 900) {
  const f = fakeChart({ spacing: 30 });
  const p = new AheadPrimitive();
  p.attached(f.param);
  p.setScene(sampleScene({ fan: null, lines: [], meet: null, hLines: [], chips: [], cloud: [], ...scene }));
  p.updateAllViews();
  const fills: { style: string; order: number }[] = [];
  const strokes: { color: string; width: number; order: number }[] = [];
  let n = 0;
  const ctx = paint(p.paneViews()[1].renderer() as never, width, 400, (c: FakeCtx) => {
    c.fill.mockImplementation(() => fills.push({ style: c.fillStyle, order: (n += 1) }));
    c.stroke.mockImplementation(() => strokes.push({ color: c.strokeStyle, width: c.lineWidth, order: (n += 1) }));
    c.fillText.mockImplementation(() => {
      n += 1;
    });
  });
  return { ctx, p, fills, strokes };
}

/** Step k's x at 30 px a step (the anchor is logical 9), and the zone's left edge (half a step past the anchor). */
const SX = (k: number) => 100 + (9 + k) * 30;
const LEFT = SX(0) + 15;

/** The chip whose words are `text`, from where its words were written (6 px a character in the fake canvas). */
function rectOf(ctx: FakeCtx, text: string): Rect | null {
  const call = ctx.fillText.mock.calls.find(c => c[0] === text);
  if (!call) return null;
  const left = (call[1] as number) - 6;
  const cy = (call[2] as number) - 0.5;
  return { left, right: left + text.length * 6 + 12, top: cy - CHIP_H / 2, bottom: cy + CHIP_H / 2 };
}

function story(points: number[], marks: StoryMark[] = [], color: string = AHEAD_COLORS.target): SceneStory {
  return { start: 5, points, marks, label: 'x', short: 'x', tiny: 'x', color,
    segments: [{ from: 0, to: 15, color, alpha: AHEAD_STORY_ALPHA.during }] };
}

const flat = (p: number) => Array.from({ length: 15 }, () => p);
const WALL = '▲ 5.20 first · 27% (forecast)';
const SUB = ['breaks 38% · 45% to 5.40 · 40% back', 'breaks 38% · 45% to 5.40', 'breaks 38%'];

describe('the zone draws its chips in three passes', () => {
  it('backings first (see-through), then the story paths over them, then the words', () => {
    const { ctx, fills, strokes } = over({ story: [story(flat(5.2))],
      chips: [{ p: 5.2, text: WALL, short: '▲ 27%', color: AHEAD_COLORS.wallAbove, role: 'wall' }] });
    const chip = rectOf(ctx, WALL) as Rect;
    expect(chip.top + CHIP_H / 2).toBe(Y(5.2));
    const backs = fills.filter(f => f.style === AHEAD_COLORS.zoneChipBg);
    expect(backs).toHaveLength(1);
    expect(AHEAD_COLORS.zoneChipBg).toBe('rgba(11, 13, 18, 0.72)');
    // The story path is drawn again over the backing, clipped to the chips, before the words go on.
    const path = strokes.filter(s => s.color === AHEAD_COLORS.target && s.width === 1.6);
    expect(path.length).toBeGreaterThan(0);
    expect(path[0].order).toBeGreaterThan(backs[0].order);
    expect(ctx.rect).toHaveBeenCalledWith(chip.left, chip.top, chip.right - chip.left, CHIP_H);
    const words = ctx.fillText.mock.invocationCallOrder[0];
    const storyStroke = ctx.stroke.mock.invocationCallOrder.find((_, i) => strokes[i] === path[0]) as number;
    expect(words).toBeGreaterThan(storyStroke);
  });

  it("puts a story path's end label beside its end, never on it", () => {
    const label = 'still open · 53% of fills (forecast)';
    const { ctx } = over({ story: [story(flat(5.1), [], AHEAD_COLORS.path)],
      chips: [{ p: 5.1, text: label, short: label, color: AHEAD_COLORS.path, role: 'story', story: 0 }] });
    const r = rectOf(ctx, label) as Rect;
    expect(r).not.toBeNull();
    const end = { a: { x: SX(12), y: Y(5.1) }, b: { x: SX(15), y: Y(5.1) } };
    expect(crosses(end, r, 0)).toBe(false);
  });
});

describe("an end label away from its end gets a leader", () => {
  // The path ends at 5.00 after a spike to 5.30 and a dip to 4.70 over its last steps: its label can sit over the
  // spike or under the dip, never at its end.
  const spiky = [...flat(5).slice(0, 12), 5.3, 4.7, 5];
  const label = 'middle case';
  const chip = { p: 5, text: label, short: label, color: AHEAD_COLORS.wallBelow, role: 'story' as const, story: 0 };
  const end = { x: SX(15), y: Y(5) };
  const leaders = (strokes: { color: string; width: number }[], color: string) =>
    strokes.filter(s => s.color === color && s.width === 1);

  it('draws a thin line in the path colour from the label edge nearest its end to that end', () => {
    const { ctx, strokes, fills } = over({ story: [story(spiky, [], AHEAD_COLORS.wallBelow)], chips: [chip] });
    const r = rectOf(ctx, label) as Rect;
    expect(r.bottom).toBeLessThan(Y(5.3));
    const from = nearestOn(r, end);
    expect(from).toEqual({ x: end.x, y: r.bottom });
    expect(ctx.moveTo).toHaveBeenCalledWith(from.x, from.y);
    expect(ctx.lineTo).toHaveBeenCalledWith(end.x, end.y);
    expect(leaders(strokes, AHEAD_COLORS.wallBelow)).toHaveLength(1);
    expect(AHEAD_STORY_ALPHA.leader).toBe(0.7);
    // With the story paths: over the chip's backing, under its words.
    const i = strokes.findIndex(s => s.color === AHEAD_COLORS.wallBelow && s.width === 1);
    const back = fills.find(f => f.style === AHEAD_COLORS.zoneChipBg) as { order: number };
    expect(strokes[i].order).toBeGreaterThan(back.order);
    expect(ctx.stroke.mock.invocationCallOrder[i]).toBeLessThan(ctx.fillText.mock.invocationCallOrder[0]);
  });

  it("sits on the side away from another story path's coloured stretch", () => {
    const above = story(flat(5.35), [], AHEAD_COLORS.wallAbove);
    const { ctx } = over({ story: [story(spiky, [], AHEAD_COLORS.wallBelow), above], chips: [chip] });
    const r = rectOf(ctx, label) as Rect;
    expect(r.top).toBeGreaterThan(Y(4.7));
    expect(ctx.moveTo).toHaveBeenCalledWith(end.x, r.top);
  });

  it('leads to the ✕ when the path has one', () => {
    const stop: StoryMark = { k: 13.5, p: 5, kind: 'stop', color: AHEAD_COLORS.stop };
    const { ctx, strokes } = over({ story: [story(spiky, [stop], AHEAD_COLORS.stop)],
      chips: [{ ...chip, color: AHEAD_COLORS.stop }] });
    const r = rectOf(ctx, label) as Rect;
    expect(leaders(strokes, AHEAD_COLORS.stop)).toHaveLength(1);
    const at = { x: SX(13.5), y: Y(5) };
    const from = nearestOn(r, at);
    expect(ctx.moveTo).toHaveBeenCalledWith(from.x, from.y);
    expect(ctx.lineTo).toHaveBeenCalledWith(at.x, at.y);
  });

  it('draws none when the label sits at its end', () => {
    const { ctx, strokes } = over({ story: [story(flat(5.1), [], AHEAD_COLORS.wallBelow)],
      chips: [{ ...chip, p: 5.1 }] });
    expect(rectOf(ctx, label)).not.toBeNull();
    expect(leaders(strokes, AHEAD_COLORS.wallBelow)).toHaveLength(0);
  });
});

describe('a chip moves, never a mark', () => {
  it("slides a wall's chip left along its price, off the diamond where a path reaches that wall", () => {
    const text = '▼ 5.00 first · 56% (forecast)';
    const mark: StoryMark = { k: 12, p: 5, kind: 'wall', color: AHEAD_COLORS.wallBelow };
    const { ctx } = over({ story: [story(flat(5), [mark], AHEAD_COLORS.wallBelow)],
      chips: [{ p: 5, text, short: '▼ 56%', color: AHEAD_COLORS.wallBelow, role: 'wall' }] });
    const r = rectOf(ctx, text) as Rect;
    expect(r.top + CHIP_H / 2).toBe(Y(5));
    const at = { left: SX(12) - 4.5, right: SX(12) + 4.5, top: Y(5) - 4.5, bottom: Y(5) + 4.5 };
    expect(overlaps(r, at, 0)).toBe(false);
    // The diamond stays where the path reaches the wall.
    expect(ctx.moveTo).toHaveBeenCalledWith(SX(12), Y(5) - 4.5);
  });

  it("moves a stub's words off the fill dot on its line", () => {
    const mark: StoryMark = { k: 14, p: 5.1, kind: 'fill', color: AHEAD_COLORS.trigger };
    const { ctx } = over({ story: [story(flat(5.1), [mark])],
      hLines: [{ p: 5.1, color: AHEAD_COLORS.trigger, dash: [6, 4], chip: 'buy-stop 5.10' }] });
    const r = rectOf(ctx, 'buy-stop 5.10') as Rect;
    const dot = { left: SX(14) - 3.2, right: SX(14) + 3.2, top: Y(5.1) - 3.2, bottom: Y(5.1) + 3.2 };
    expect(overlaps(r, dot, 0)).toBe(false);
    expect(r.top + CHIP_H / 2).toBe(Y(5.1) - 11);
    expect(ctx.arc.mock.calls.some(([x, y, rad]) => x === SX(14) && y === Y(5.1) && rad === 3.2)).toBe(true);
  });

  it("lifts a stub's words further off its line when marks along it leave no gap to slide into", () => {
    const marks: StoryMark[] = [14, 11, 8, 5, 2].map(k => ({ k, p: 5.1, kind: 'fill', color: AHEAD_COLORS.trigger }));
    const { ctx } = over({ story: [story(flat(5.1), marks)],
      hLines: [{ p: 5.1, color: AHEAD_COLORS.trigger, dash: [6, 4], chip: 'buy-stop 5.10' }] });
    const r = rectOf(ctx, 'buy-stop 5.10') as Rect;
    expect(r.top + CHIP_H / 2).toBe(Y(5.1) - 18);
    for (const k of [14, 11, 8, 5, 2]) {
      expect(overlaps(r, { left: SX(k) - 3.2, right: SX(k) + 3.2, top: Y(5.1) - 3.2, bottom: Y(5.1) + 3.2 }, 0))
        .toBe(false);
    }
  });
});

describe("a wall's 'if it breaks' line", () => {
  const wall = { p: 5.2, text: WALL, short: '▲ 27%', color: AHEAD_COLORS.wallAbove, role: 'wall' as const, sub: SUB };

  it('takes the longest words no wider than 60% of the zone', () => {
    // A zone 320 px wide: the full line (228 px) is over 60% of it, the middle one (156 px) is not.
    const { ctx, p } = over({ chips: [wall] }, LEFT + 320);
    expect(p.px?.left).toBe(LEFT);
    const zone = 320;
    expect(rectOf(ctx, SUB[0])).toBeNull();
    const r = rectOf(ctx, SUB[1]) as Rect;
    expect(r).not.toBeNull();
    expect(r.right - r.left).toBeLessThanOrEqual(SUB_MAX_SHARE * zone);
    expect(rectOf(ctx, WALL)).not.toBeNull();
  });

  it("is left to the walls card when it would sit on a story path's coloured stretch", () => {
    // A path zigzags through both rows the line could take, under and over the wall's chip.
    const zig = Array.from({ length: 15 }, (_, i) => (i % 2 ? 5.3 : 5.1));
    const { ctx } = over({ story: [story(zig, [], AHEAD_COLORS.wallAbove)], chips: [wall] });
    expect(rectOf(ctx, WALL)).not.toBeNull();
    for (const t of SUB) expect(rectOf(ctx, t)).toBeNull();
    // A faded stretch does not count: the line is drawn.
    const faded = story(zig, [], AHEAD_COLORS.wallAbove);
    faded.segments = [{ from: 0, to: 15, color: AHEAD_COLORS.wallAbove, alpha: AHEAD_STORY_ALPHA.after }];
    expect(rectOf(over({ story: [faded], chips: [wall] }).ctx, SUB[0])).not.toBeNull();
  });
});
