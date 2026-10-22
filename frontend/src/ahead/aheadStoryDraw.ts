/**
 * The pixels of Ahead's paths (ADR 065), for `AheadZoneRenderer`: the soft cloud of every path, then the story paths
 * over it stage by stage (grey, coloured, faded); over the zone's other drawing, the story paths again inside the
 * chips' backings (so no chip hides one) and their marks. Pixel work only: every colour, strength and step was decided
 * in the scene (`aheadStory.ts`). A fractional step sits on the straight line between its two whole steps, so a mark
 * always lands on the line it marks. The chips' layout reads the marks' and the coloured stretches' pixels from here,
 * and each end label's anchor (its path's end, or its ✓ / ✕); a label placed away from it gets a thin leader to it.
 */
import { AHEAD_COLORS, AHEAD_STORY_ALPHA, AHEAD_STORY_GLYPH } from './aheadConstants';
import { diamond, dot, glyph, polyline, type Pt, type Rect, type Seg } from './aheadCanvas';
import type { SceneStory, StoryMark } from './aheadSceneTypes';
import type { Px } from './AheadZoneRenderer';

const CLOUD_WIDTH_PX = 1;
const STORY_WIDTH_PX = 1.6;
const FILL_DOT_PX = 3.2;
/** The thin line from an end label that could not sit at its end to that end. */
const LEADER_WIDTH_PX = 1;
/** The diamond where a story path first reaches a wall: half its diagonal. */
const WALL_DIAMOND_PX = 4.5;
/** The dark disc under a ✓ / ✕. */
const GLYPH_BACK_PX = 6.5;
/** How far a mark reaches from its point, by kind (the chips keep clear of it). */
const MARK_R: Record<StoryMark['kind'], number> = {
  fill: FILL_DOT_PX, wall: WALL_DIAMOND_PX, target: GLYPH_BACK_PX, stop: GLYPH_BACK_PX,
};
/** An end label keeps off its own path over this many last steps, so it sits beside the path's end, not on it. */
const END_STEPS = 3;

/** A path's pixels from the anchor (index 0) to its last step; null where a step is off the time scale. `start`: the
 * price at step 0 (a story path's, the one its crossings were counted from), at the anchor's x; absent, the anchor. */
export function pathPts(px: Px, points: readonly number[], start?: number): (Pt | null)[] {
  const y0 = start === undefined ? null : px.y(start);
  const out: (Pt | null)[] = [y0 === null ? px.anchor : { x: px.anchor.x, y: y0 }];
  points.forEach((p, i) => {
    const x = px.xs.get(i + 1);
    const y = px.y(p);
    out.push(x !== undefined && y !== null ? { x, y } : null);
  });
  return out;
}

/** The point at fractional step `k` on the line through the whole steps; null when either neighbour is unplaced. */
export function ptAt(pts: readonly (Pt | null)[], k: number): Pt | null {
  const lo = Math.max(0, Math.min(pts.length - 1, Math.floor(k)));
  const hi = Math.min(pts.length - 1, lo + 1);
  const a = pts[lo];
  const b = pts[hi];
  if (!a || !b) return null;
  const f = Math.max(0, Math.min(1, k - lo));
  return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
}

/** The stretch `from..to` of a path's pixels, its ends placed between whole steps. */
export function stretch(pts: readonly (Pt | null)[], from: number, to: number): Pt[] {
  const out: Pt[] = [];
  const push = (p: Pt | null) => {
    if (p) out.push(p);
  };
  push(ptAt(pts, from));
  for (let i = Math.floor(from) + 1; i < to; i += 1) push(pts[i] ?? null);
  push(ptAt(pts, to));
  return out;
}

/** Every path, one faint stroke each, so overlap builds density and no one path stands out; no outcome colour. */
export function drawCloud(ctx: CanvasRenderingContext2D, px: Px): void {
  for (const points of px.scene.cloud) {
    const pts = pathPts(px, points).filter((p): p is Pt => p !== null);
    polyline(ctx, pts, AHEAD_COLORS.path, AHEAD_STORY_ALPHA.cloud, CLOUD_WIDTH_PX);
  }
}

/** One story path stage by stage (under the candles, with the cloud). */
export function drawStory(ctx: CanvasRenderingContext2D, px: Px, story: SceneStory): void {
  const pts = pathPts(px, story.points, story.start);
  for (const s of story.segments) polyline(ctx, stretch(pts, s.from, s.to), s.color, s.alpha, STORY_WIDTH_PX);
}

/** Each story mark's point on the pane, inside the price area only (`bottom`: the volume band's top). */
function markPts(px: Px, story: SceneStory, bottom: number): { m: StoryMark; at: Pt }[] {
  const pts = pathPts(px, story.points, story.start);
  return story.marks.flatMap((m) => {
    const at = ptAt(pts, m.k);
    return at && at.y >= 0 && at.y <= bottom ? [{ m, at }] : [];
  });
}

/** A story path's marks, over everything else of the zone but the chips' words: a dot at the fill, a filled diamond
 * where it first reaches a wall, a ✓ / ✕ on a small backing disc so it reads on any line. */
export function drawMarks(ctx: CanvasRenderingContext2D, px: Px, story: SceneStory, bottom: number): void {
  for (const { m, at } of markPts(px, story, bottom)) {
    if (m.kind === 'fill') dot(ctx, at, FILL_DOT_PX, m.color);
    else if (m.kind === 'wall') diamond(ctx, at, WALL_DIAMOND_PX, m.color, AHEAD_COLORS.chipBg);
    else {
      dot(ctx, at, GLYPH_BACK_PX, AHEAD_COLORS.chipBg);
      glyph(ctx, at, AHEAD_STORY_GLYPH[m.kind], m.color);
    }
  }
}

/** The square each drawn mark takes, for the chips to keep clear of: a chip moves, never a mark. */
export function markRects(px: Px, bottom: number): Rect[] {
  return px.scene.story.flatMap((story) => markPts(px, story, bottom).map(({ m, at }) => {
    const r = MARK_R[m.kind];
    return { left: at.x - r, right: at.x + r, top: at.y - r, bottom: at.y + r };
  }));
}

function segsOf(pts: Pt[]): Seg[] {
  return pts.slice(1).map((b, i) => ({ a: pts[i], b }));
}

/** Every story path's coloured stretches (a trade on, or past its first wall), as straight pieces on the pane;
 * `except`: leave out story path `except`'s own. */
export function colouredSegs(px: Px, except?: number): Seg[] {
  return px.scene.story.flatMap((story, i) => {
    if (i === except) return [];
    const pts = pathPts(px, story.points, story.start);
    return story.segments.filter((s) => s.alpha === AHEAD_STORY_ALPHA.during)
      .flatMap((s) => segsOf(stretch(pts, s.from, s.to)));
  });
}

/** Story path `i`'s last steps, whatever their stage: its end label keeps off them. */
export function endSegs(px: Px, i: number): Seg[] {
  const story = px.scene.story[i];
  if (!story) return [];
  const pts = pathPts(px, story.points, story.start);
  const n = story.points.length;
  return segsOf(stretch(pts, Math.max(0, n - END_STEPS), n));
}

/** Where story path `i`'s end label belongs: its ✓ / ✕ when it has one, else its last step; `r`, how far that mark
 * reaches from its point (0 at a bare end). Null when the point is off the price area (its caret marks it there). */
export function endAnchor(px: Px, i: number, bottom: number): { at: Pt; r: number } | null {
  const story = px.scene.story[i];
  if (!story) return null;
  const pts = pathPts(px, story.points, story.start);
  const exit = story.marks.find((m) => m.kind === 'target' || m.kind === 'stop');
  const at = exit ? ptAt(pts, exit.k) : pts[pts.length - 1];
  if (!at || at.y < 0 || at.y > bottom) return null;
  return { at, r: exit ? MARK_R[exit.kind] : 0 };
}

/** The leaders from end labels that could not sit at their end to that end (or its ✓ / ✕): thin, in the path's
 * colour, drawn with the story paths -- over the chips' backings, under their words and the marks. */
export function drawLeaders(ctx: CanvasRenderingContext2D,
  leaders: readonly { from: Pt; to: Pt; color: string }[]): void {
  for (const l of leaders) polyline(ctx, [l.from, l.to], l.color, AHEAD_STORY_ALPHA.leader, LEADER_WIDTH_PX);
}

/** The story paths again, inside the chips' backings only (they were drawn under the candles, and a backing would
 * dim them): a chip never hides a story path, and its words go on top. `bottom`: the price area's. */
export function drawStoryInChips(ctx: CanvasRenderingContext2D, px: Px, chips: readonly Rect[], right: number,
  bottom: number): void {
  if (chips.length === 0 || px.scene.story.length === 0) return;
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, right, bottom);
  ctx.clip();
  ctx.beginPath();
  for (const r of chips) ctx.rect(r.left, r.top, r.right - r.left, r.bottom - r.top);
  ctx.clip();
  for (const story of px.scene.story) drawStory(ctx, px, story);
  ctx.restore();
}

/** The stage a story path is in at step `k`: its colour and strength there. */
export function stageAt(story: SceneStory, k: number): { color: string; alpha: number } {
  const s = story.segments.find((g) => k >= g.from && k <= g.to) ?? story.segments[story.segments.length - 1];
  return s ? { color: s.color, alpha: s.alpha } : { color: story.color, alpha: AHEAD_STORY_ALPHA.before };
}
