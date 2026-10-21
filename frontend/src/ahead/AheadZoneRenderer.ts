/**
 * The pixels of Ahead's zone on the 1-minute pane (ADR 065), for `AheadPrimitive`: under the candles the hatched zone,
 * the forecaster's fan and its drawn paths; over them Nova's lines to the meet, the stubs and every chip.
 *
 * The fan and the paths stay in the price area: they are clipped at the top of the volume band (the volume overlay's
 * scale margin) so a forecast never runs over the real or ghost volume bars, and a path that leaves the price area
 * (under that band's top, or over the pane's top) gets a small caret at the edge it left by. Chips stay inside the
 * zone: the full words, else the short ones, else none; a wall's "if it breaks" second line only when it fits too.
 * A price's chip (a wall's, a strategy's) is placed first, on its price; the "neither" chip, tied to no one price,
 * yields: it is placed last, in the free space between the walls (`freeSpot`), or left to the panel's card.
 */
import {
  AHEAD_DRAW, band, chip, CHIP_H, chipWidth, crosses, dashed, hatch, overlaps, polyline, ring, topOver, type Pt, type Rect,
  type Seg,
} from './aheadCanvas';
import type { AheadScene } from './aheadSceneTypes';
import type { ZoneLayout } from './AheadPrimitive';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';

const MEET_RING_PX = 6;
/** The meet's chip keeps this clear of its ring and of the lines that run into it. */
const MEET_CHIP_GAP_PX = 5;
const CHIP_GAP_PX = 2;
const CHIP_STEP_PX = 20;
/** The "neither" chip looks for free space this many pixels at a time, outward from the middle it asks for. */
const FREE_STEP_PX = 2;
/** Chips keep this far inside the zone's edges. */
const CHIP_INSET_PX = 4;
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

/** One caret per path at the first step it leaves the price area by (under `bottom` or over the pane's top). */
export function pathCarets(px: Px, bottom: number): { x: number; down: boolean; color: string; alpha: number }[] {
  const out: { x: number; down: boolean; color: string; alpha: number }[] = [];
  for (const path of px.scene.paths) {
    for (let i = 0; i < path.points.length; i += 1) {
      const x = px.xs.get(i + 1);
      const y = px.y(path.points[i]);
      if (x === undefined || y === null || (y <= bottom && y >= 0)) continue;
      out.push({ x, down: y > bottom, color: path.color, alpha: Math.max(path.alpha, CARET_MIN_ALPHA) });
      break;
    }
  }
  return out;
}

/**
 * Where a chip tied to no one price goes: the centre nearest `want` between `top` and `bottom` (the walls' lines, or
 * the price area's edges) whose chip `clear` accepts, its whole height inside that space; null when none is free.
 */
export function freeSpot(want: number, top: number, bottom: number, clear: (cy: number) => boolean): number | null {
  const lo = top + CHIP_H / 2;
  const hi = bottom - CHIP_H / 2;
  if (hi < lo) return null;
  const start = Math.min(hi, Math.max(lo, want));
  for (let d = 0; start - d >= lo || start + d <= hi; d += FREE_STEP_PX) {
    for (const cy of d === 0 ? [start] : [start - d, start + d]) {
      if (cy >= lo && cy <= hi && clear(cy)) return cy;
    }
  }
  return null;
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
    for (const path of s.paths) {
      const pts: Pt[] = [px.anchor];
      path.points.forEach((p, i) => {
        const x = px.xs.get(i + 1);
        const y = px.y(p);
        if (x !== undefined && y !== null) pts.push({ x, y });
      });
      polyline(ctx, pts, path.color, path.alpha);
    }
    ctx.restore();
    for (const c of pathCarets(px, bottom)) {
      if (c.x >= px.left && c.x <= right) caret(ctx, c.x, c.down ? bottom : 0, c.down, c.color, c.alpha);
    }
  }

  /** The lines, the stubs and every chip; returns the rectangles its words hold. */
  private over(ctx: CanvasRenderingContext2D, px: Px, right: number, W: number, H: number): Rect[] {
    const s = px.scene;
    const bounds = { width: Math.min(W, right + 1), height: H };
    const rects: Rect[] = [];
    const put = (r: Rect | null) => {
      if (r) rects.push(r);
    };
    // Words that fit the zone: the full words, else the short ones, slid inside the zone; none when neither fits. A
    // chip is never drawn left of the zone, over real candles.
    const lo = px.left + CHIP_INSET_PX;
    const hi = right - CHIP_INSET_PX;
    const fit = (xEnd: number, text: string, short: string): { end: number; text: string; w: number } | null => {
      for (const t of [text, short]) {
        const w = chipWidth(ctx, t);
        if (w > hi - lo) continue;
        return { end: Math.min(hi, Math.max(lo + w, xEnd)), text: t, w };
      }
      return null;
    };
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
    if (s.meet) {
      const xm = at(Math.min(s.meet.steps, s.horizon));
      const ym = px.y(s.meet.p);
      if (xm !== null && ym !== null) {
        if (s.meet.inZone) ring(ctx, { x: xm, y: ym }, MEET_RING_PX, AHEAD_DRAW.ring);
        // Over the ring, and over the lines that run into it, with room to spare: never on either.
        const f = fit(xm + chipWidth(ctx, s.meet.text) / 2, s.meet.text, s.meet.text);
        if (f) {
          const roof = Math.min(ym - MEET_RING_PX, topOver(segs, f.end - f.w, f.end));
          // A steep line could push it off the pane: it then stops at the pane's top.
          const cy = Math.max(CHIP_H / 2 + 1, roof - MEET_CHIP_GAP_PX - CHIP_H / 2);
          put(chip(ctx, f.end, cy, f.text, AHEAD_DRAW.text, AHEAD_DRAW.chipBg, 'end', bounds));
        }
      }
    }
    for (const h of s.hLines) {
      const y = px.y(h.p);
      if (y === null) continue;
      dashed(ctx, { x: px.left, y }, { x: right, y }, h.color, h.dash, 1.6);
      const f = h.chip ? fit(hi, h.chip, h.chip) : null;
      if (f) put(chip(ctx, f.end, y - 11, f.text, h.color, AHEAD_DRAW.chipBg, 'end', bounds));
    }
    // The odds chips at the zone's right edge, none covering another or sitting on Nova's lines. A price's chip first,
    // top to bottom, on its price (nudged down only past what is already there); "neither" last, in the free space
    // between the walls nearest the middle it asks for -- it never pushes a wall's chip off its wall.
    const placed: Rect[] = [...rects];
    const clear = (r: Rect) => !placed.some(q => overlaps(q, r, CHIP_GAP_PX))
      && !segs.some(g => crosses(g, r, CHIP_GAP_PX));
    const located = s.chips.flatMap(c => {
      const y = px.y(c.p);
      return y === null ? [] : [{ c, y }];
    });
    const priced = located.filter(x => x.c.role !== 'neither').sort((a, b) => a.y - b.y);
    const wallYs = located.filter(x => x.c.role === 'wall').map(x => x.y);
    const floor = Math.min(H, px.priceBottom ?? H);
    for (const { c, y } of [...priced, ...located.filter(x => x.c.role === 'neither')]) {
      const f = fit(hi, c.text, c.short);
      if (!f) continue;
      // The chip alone finds its place first; its second line never moves it.
      const left = f.end - f.w;
      const box = (cy: number): Rect => ({ left, right: f.end, top: cy - CHIP_H / 2, bottom: cy + CHIP_H / 2 });
      let cy = y;
      if (c.role === 'neither') {
        const top = Math.max(0, ...wallYs.filter(w => w < y));
        const bottom = Math.min(floor, ...wallYs.filter(w => w > y));
        const spot = freeSpot(y, top, bottom, v => clear(box(v)));
        if (spot === null) continue;
        cy = spot;
      } else {
        for (let tries = 0; tries < 8; tries += 1) {
          if (clear(box(cy))) break;
          cy += CHIP_STEP_PX;
        }
      }
      const main = chip(ctx, f.end, cy, f.text, c.color, AHEAD_DRAW.chipBg, 'end', bounds);
      // A wall's "if it breaks" line: beside the full words only, under the chip or else over it, and only where it
      // fits as placed. Otherwise the walls card alone carries it.
      const subW = c.sub ? chipWidth(ctx, c.sub) : 0;
      const subEnd = Math.min(hi, Math.max(lo + subW, f.end));
      // It sits flush on its own chip, so only the others (and the pane's edges) can refuse it.
      const spot = !main || !c.sub || f.text !== c.text || subW > hi - lo ? undefined
        : [cy + CHIP_H, cy - CHIP_H].find(sy => sy - CHIP_H / 2 >= 0 && sy + CHIP_H / 2 <= H
          && clear({ left: subEnd - subW, right: subEnd, top: sy - CHIP_H / 2, bottom: sy + CHIP_H / 2 }));
      const second = c.sub && spot !== undefined
        ? chip(ctx, subEnd, spot, c.sub, c.color, AHEAD_DRAW.chipBg, 'end', bounds) : null;
      for (const r of [main, second]) {
        if (r) {
          placed.push(r);
          rects.push(r);
        }
      }
    }
    return rects;
  }
}
