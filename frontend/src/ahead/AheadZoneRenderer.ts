/**
 * The pixels of Ahead's zone on the 1-minute pane (ADR 065), for `AheadPrimitive`: under the candles the hatched zone,
 * the forecaster's fan, the soft cloud of its paths and the story paths over it (`aheadStoryDraw.ts`); over them Nova's
 * lines to the meet, the stubs and every chip, in three passes: the chips' see-through backings, the story paths again
 * inside them, the end labels' leaders and every mark, then the chips' words -- a chip never hides a story path, and
 * no mark sits under words.
 *
 * The fan and the paths stay in the price area: they are clipped at the top of the volume band (the volume overlay's
 * scale margin) so a forecast never runs over the real or ghost volume bars, and a story path that leaves the price
 * area (under that band's top, or over the pane's top) gets a small caret at the edge it left by. Chips stay inside the
 * zone; where each goes is `aheadZoneChips.ts`'s (a chip moves, never a mark).
 */
import { AHEAD_DRAW, band, chipBack, chipText, dashed, hatch, ring, type Pt, type Rect, type Seg } from './aheadCanvas';
import type { AheadScene } from './aheadSceneTypes';
import { drawCloud, drawLeaders, drawMarks, drawStory, drawStoryInChips, stageAt } from './aheadStoryDraw';
import { layoutChips } from './aheadZoneChips';
import type { ZoneLayout } from './AheadPrimitive';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';

export { freeSpot } from './aheadZoneChips';

const MEET_RING_PX = 6;
/** The caret marking a path that leaves the price area: half its width, its height. */
const CARET_PX = 3;
/** A caret is drawn at least this strong, so a faint path's still reads. */
const CARET_MIN_ALPHA = 0.6;

/** Where a zone's parts go on the pane, in its media pixels. */
export interface Px {
  anchor: Pt;
  /** Zone left (the anchor candle's right edge) and its unclipped right (just past the last step's ghost bar). */
  left: number;
  right: number;
  xs: Map<number, number>;
  y: (p: number) => number | null;
  /** The price area's bottom: the top of the volume band (null: the pane's own bottom). */
  priceBottom: number | null;
  scene: AheadScene;
}

/** What the renderer reads from its primitive. */
export interface ZoneSource {
  readonly px: Px | null;
  readonly fanDim: boolean;
  stepX(k: number): number | null;
  drawn(zone: ZoneLayout, rects: Rect[]): void;
}

/** One caret per story path at the first step it leaves the price area by (under `bottom` or over the pane's top), in
 * its stage's colour there. The cloud gets none: it is clipped, and the story paths carry the read. */
export function pathCarets(px: Px, bottom: number): { x: number; down: boolean; color: string; alpha: number }[] {
  const out: { x: number; down: boolean; color: string; alpha: number }[] = [];
  for (const story of px.scene.story) {
    for (let i = 0; i < story.points.length; i += 1) {
      const x = px.xs.get(i + 1);
      const y = px.y(story.points[i]);
      if (x === undefined || y === null || (y <= bottom && y >= 0)) continue;
      const stage = stageAt(story, i + 1);
      out.push({ x, down: y > bottom, color: stage.color, alpha: Math.max(stage.alpha, CARET_MIN_ALPHA) });
      break;
    }
  }
  return out;
}

function caret(ctx: CanvasRenderingContext2D, x: number, edge: number, down: boolean, color: string, alpha: number) {
  const tip = down ? edge - 1 : edge + 1;
  const base = down ? tip - CARET_PX : tip + CARET_PX;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(x - CARET_PX, base);
  ctx.lineTo(x, tip);
  ctx.lineTo(x + CARET_PX, base);
  ctx.stroke();
  ctx.restore();
}

export class AheadRenderer implements IPrimitivePaneRenderer {
  private readonly src: ZoneSource;
  private readonly layer: 'under' | 'over';

  constructor(src: ZoneSource, layer: 'under' | 'over') {
    this.src = src;
    this.layer = layer;
  }

  draw(target: CanvasRenderingTarget2D): void {
    const px = this.src.px;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width;
      const H = mediaSize.height;
      if (!px) {
        if (this.layer === 'over') this.src.drawn(null, []);
        return;
      }
      // The full 15 steps, every pane alike; only the pane's own edge cuts it.
      const right = Math.min(px.right, W);
      if (right <= px.left) {
        if (this.layer === 'over') this.src.drawn(null, []);
        return;
      }
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, right, H);
      ctx.clip();
      if (this.layer === 'under') {
        this.under(ctx, px, right, H);
        ctx.restore();
        return;
      }
      const rects = this.over(ctx, px, right, W, H);
      ctx.restore();
      this.src.drawn({ left: px.left, right, top: 0 }, rects);
    });
  }

  private under(ctx: CanvasRenderingContext2D, px: Px, right: number, H: number): void {
    const s = px.scene;
    hatch(ctx, { left: px.left, top: 0, right, bottom: H }, AHEAD_DRAW.zone, AHEAD_DRAW.stripe);
    dashed(ctx, { x: px.left, y: 0 }, { x: px.left, y: H }, AHEAD_DRAW.muted, [3, 3], 1);
    // The forecast's prices stay in the price area, never over the volume band under it.
    const bottom = Math.min(H, px.priceBottom ?? H);
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, right, bottom);
    ctx.clip();
    const steps = (s.fan ?? []).filter(b => px.xs.has(b.k));
    if (steps.length) {
      const xs = steps.map(b => px.xs.get(b.k) as number);
      const ys = (pick: (b: (typeof steps)[number]) => number) => steps.map(b => px.y(pick(b)) ?? px.anchor.y);
      const dim = this.src.fanDim ? AHEAD_DRAW.fanDim : 1;
      band(ctx, px.anchor, xs, ys(b => b.q90), ys(b => b.q10), AHEAD_DRAW.ai, AHEAD_DRAW.fanOuter * dim);
      band(ctx, px.anchor, xs, ys(b => b.q75), ys(b => b.q25), AHEAD_DRAW.ai, AHEAD_DRAW.fanInner * dim);
    }
    drawCloud(ctx, px);
    for (const story of s.story) drawStory(ctx, px, story);
    ctx.restore();
    for (const c of pathCarets(px, bottom)) {
      if (c.x >= px.left && c.x <= right) caret(ctx, c.x, c.down ? bottom : 0, c.down, c.color, c.alpha);
    }
  }

  /** The lines and the stubs, then every chip in three passes -- their backings, the story paths and their marks over
   * the backings, their words on top -- so a chip never hides a story path and no mark is ever under words. Returns
   * the rectangles its words hold. */
  private over(ctx: CanvasRenderingContext2D, px: Px, right: number, W: number, H: number): Rect[] {
    const s = px.scene;
    const at = (k: number) => this.src.stepX(k);
    const segs: Seg[] = [];
    for (const line of s.lines) {
      const xb = at(line.toSteps);
      const ya = px.y(line.fromP);
      const yb = px.y(line.fromP + line.slope * line.toSteps);
      if (xb === null || ya === null || yb === null) continue;
      dashed(ctx, { x: px.anchor.x, y: ya }, { x: xb, y: yb }, line.color, [2, 5], 2, true);
      segs.push({ a: { x: px.anchor.x, y: ya }, b: { x: xb, y: yb } });
    }
    let meetAt: { x: number; y: number } | null = null;
    if (s.meet) {
      const xm = at(Math.min(s.meet.steps, s.horizon));
      const ym = px.y(s.meet.p);
      if (xm !== null && ym !== null) {
        if (s.meet.inZone) ring(ctx, { x: xm, y: ym }, MEET_RING_PX, AHEAD_DRAW.ring);
        meetAt = { x: xm, y: ym };
      }
    }
    for (const h of s.hLines) {
      const y = px.y(h.p);
      if (y !== null) dashed(ctx, { x: px.left, y }, { x: right, y }, h.color, h.dash, 1.6);
    }
    const floor = Math.min(H, px.priceBottom ?? H);
    const chips = layoutChips(ctx, { px, right, W, H, floor, segs, meetAt });
    const rects = chips.map(c => c.rect);
    for (const c of chips) chipBack(ctx, c.rect, AHEAD_DRAW.zoneChipBg);
    drawStoryInChips(ctx, px, rects, right, floor);
    drawLeaders(ctx, chips.flatMap(c => (c.leader ? [c.leader] : [])));
    for (const story of s.story) drawMarks(ctx, px, story, floor);
    for (const c of chips) chipText(ctx, c.rect, c.text, c.fg);
    return rects;
  }
}
