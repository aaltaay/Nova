/**
 * Canvas strokes for Ahead's drawing (ADR 065): the hatched "drawn, never recorded" zone, a filled band between two
 * price runs, a polyline, a dashed line and a chip of words. Pure pixel work in the pane's media space; every word
 * and colour arrives from the scene (`aheadScene.ts`) or `aheadConstants.ts`.
 */
import { AHEAD_COLORS, AHEAD_FAN_DIM } from './aheadConstants';

/** The drawing's colours (`aheadConstants.ts`) and strengths (the mockup's). */
export const AHEAD_DRAW = {
  zone: AHEAD_COLORS.hatch,
  stripe: AHEAD_COLORS.hatchStripe,
  ai: AHEAD_COLORS.ai,
  aiText: AHEAD_COLORS.heading,
  text: AHEAD_COLORS.text,
  muted: AHEAD_COLORS.muted,
  ring: AHEAD_COLORS.meetRing,
  chipBg: AHEAD_COLORS.chipBg,
  zoneChipBg: AHEAD_COLORS.zoneChipBg,
  /** The fan's outer (10-90) and inner (25-75) band strengths; a strategy scope dims both by `AHEAD_FAN_DIM`. */
  fanOuter: 0.13,
  fanInner: 0.24,
  fanDim: AHEAD_FAN_DIM,
  /** The MACD fan's band strengths. */
  macdOuter: 0.14,
  macdInner: 0.26,
  /** Ghost volume: the q50 outline's fill and the whisker's strength. */
  volumeFill: 0.1,
  volumeWhisker: 0.7,
} as const;

export interface Pt {
  x: number;
  y: number;
}

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** Stripe period at right angles to the stripes (px) and their width: the mockup's 9 px pattern turned 45°. */
const HATCH_PERIOD_PX = 9;
const HATCH_STRIPE_PX = 3;
const CHIP_FONT = '600 11px ui-sans-serif, system-ui, sans-serif';
export const CHIP_H = 18;
const CHIP_PAD_PX = 6;
const CHIP_RADIUS_PX = 4;

/** The zone: a flat fill with faint 45° stripes over it, clipped to the rectangle. */
export function hatch(ctx: CanvasRenderingContext2D, r: Rect, fill: string, stripe: string): void {
  const w = r.right - r.left;
  const h = r.bottom - r.top;
  if (w <= 0 || h <= 0) return;
  ctx.save();
  ctx.fillStyle = fill;
  ctx.fillRect(r.left, r.top, w, h);
  ctx.beginPath();
  ctx.rect(r.left, r.top, w, h);
  ctx.clip();
  ctx.strokeStyle = stripe;
  ctx.lineWidth = HATCH_STRIPE_PX;
  ctx.beginPath();
  // Stripes fixed to the pane, not the zone, so they do not crawl as the zone's edge moves.
  const step = HATCH_PERIOD_PX * Math.SQRT2;
  const start = Math.floor((r.left - h) / step) * step;
  for (let x = start; x <= r.right; x += step) {
    ctx.moveTo(x, r.bottom);
    ctx.lineTo(x + h, r.top);
  }
  ctx.stroke();
  ctx.restore();
}

/** A band from `from` through the upper run and back along the lower one (same x's, oldest first). */
export function band(ctx: CanvasRenderingContext2D, from: Pt, xs: number[], hi: number[], lo: number[],
  color: string, alpha: number): void {
  if (xs.length === 0) return;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  for (let i = 0; i < xs.length; i += 1) ctx.lineTo(xs[i], hi[i]);
  for (let i = xs.length - 1; i >= 0; i -= 1) ctx.lineTo(xs[i], lo[i]);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

export function polyline(ctx: CanvasRenderingContext2D, pts: Pt[], color: string, alpha: number, width = 1): void {
  if (pts.length < 2) return;
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i += 1) ctx.lineTo(pts[i].x, pts[i].y);
  ctx.stroke();
  ctx.restore();
}

export function dashed(ctx: CanvasRenderingContext2D, a: Pt, b: Pt, color: string, dash: number[], width = 1.6,
  round = false): void {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  if (round) ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.lineTo(b.x, b.y);
  ctx.stroke();
  ctx.restore();
}

export function ring(ctx: CanvasRenderingContext2D, at: Pt, r: number, color: string): void {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.6;
  ctx.beginPath();
  ctx.arc(at.x, at.y, r, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

/** A filled dot (a story path's fill). */
export function dot(ctx: CanvasRenderingContext2D, at: Pt, r: number, color: string): void {
  ctx.save();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(at.x, at.y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

/** A filled diamond with a thin dark edge, so it reads on its own line (where a story path first reaches a wall:
 * never a ring, which is the meet's). */
export function diamond(ctx: CanvasRenderingContext2D, at: Pt, r: number, color: string, edge: string): void {
  ctx.save();
  ctx.fillStyle = color;
  ctx.strokeStyle = edge;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(at.x, at.y - r);
  ctx.lineTo(at.x + r, at.y);
  ctx.lineTo(at.x, at.y + r);
  ctx.lineTo(at.x - r, at.y);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

/** One character centred on a point (a story path's ✓ / ✕ exit). */
export function glyph(ctx: CanvasRenderingContext2D, at: Pt, text: string, color: string): void {
  ctx.save();
  ctx.font = '700 12px ui-sans-serif, system-ui, sans-serif';
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, at.x, at.y);
  ctx.restore();
}

/** How wide a chip of these words is (px), without drawing it. */
export function chipWidth(ctx: CanvasRenderingContext2D, text: string): number {
  ctx.save();
  ctx.font = CHIP_FONT;
  const w = ctx.measureText(text).width + 2 * CHIP_PAD_PX;
  ctx.restore();
  return w;
}

/** A chip's rectangle `w` wide (its right edge at `end`, its centre at `cy`). */
export function chipRect(end: number, w: number, cy: number): Rect {
  return { left: end - w, right: end, top: cy - CHIP_H / 2, bottom: cy + CHIP_H / 2 };
}

/** The rectangle lies wholly on the pane. */
export function onPane(r: Rect, bounds: { width: number; height: number }): boolean {
  return r.left >= 0 && r.top >= 0 && r.right <= bounds.width && r.bottom <= bounds.height;
}

/** A chip's rounded backing (drawn apart from its words, so a story path can be drawn between the two). */
export function chipBack(ctx: CanvasRenderingContext2D, r: Rect, bg: string): void {
  ctx.save();
  ctx.fillStyle = bg;
  ctx.beginPath();
  if (typeof ctx.roundRect === 'function') ctx.roundRect(r.left, r.top, r.right - r.left, CHIP_H, CHIP_RADIUS_PX);
  else ctx.rect(r.left, r.top, r.right - r.left, CHIP_H);
  ctx.fill();
  ctx.restore();
}

/** A chip's words, on the backing `chipBack` drew in the same rectangle. */
export function chipText(ctx: CanvasRenderingContext2D, r: Rect, text: string, fg: string): void {
  ctx.save();
  ctx.font = CHIP_FONT;
  ctx.fillStyle = fg;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, r.left + CHIP_PAD_PX, (r.top + r.bottom) / 2 + 0.5);
  ctx.restore();
}

/**
 * Words on a rounded chip. `anchor` says which edge `x` is: 'end' puts the chip's right edge there. `y` is the chip's
 * vertical centre. Returns the rectangle it holds (for the pane's words), or null when it would not fit the pane.
 */
export function chip(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, fg: string, bg: string,
  anchor: 'start' | 'end', bounds: { width: number; height: number }): Rect | null {
  const w = chipWidth(ctx, text);
  const r = chipRect(anchor === 'end' ? x : x + w, w, y);
  if (!onPane(r, bounds)) return null;
  chipBack(ctx, r, bg);
  chipText(ctx, r, text, fg);
  return r;
}

/** Small words with no chip (the minute labels, a pane's caption). */
export function words(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, color: string,
  align: CanvasTextAlign = 'center', font = '11px ui-sans-serif, system-ui, sans-serif'): void {
  ctx.save();
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(text, x, y);
  ctx.restore();
}

/** A straight line drawn on the pane (Nova's lines carried on to the meet). */
export interface Seg {
  a: Pt;
  b: Pt;
}

/** The segment's y range over the columns `left..right` (null when it does not reach them). */
function segYs(seg: Seg, left: number, right: number): [number, number] | null {
  const x0 = Math.min(seg.a.x, seg.b.x);
  const x1 = Math.max(seg.a.x, seg.b.x);
  const lo = Math.max(left, x0);
  const hi = Math.min(right, x1);
  if (lo > hi) return null;
  const at = (x: number) => (x1 === x0 ? seg.a.y : seg.a.y + ((seg.b.y - seg.a.y) * (x - seg.a.x)) / (seg.b.x - seg.a.x));
  const ya = at(lo);
  const yb = at(hi);
  return [Math.min(ya, yb), Math.max(ya, yb)];
}

/** A chip's rectangle would sit on the segment (with `gap` px kept free around it). */
export function crosses(seg: Seg, r: Rect, gap = 2): boolean {
  const ys = segYs(seg, r.left - gap, r.right + gap);
  return !!ys && ys[0] < r.bottom + gap && ys[1] > r.top - gap;
}

/** The highest point (smallest y) any segment reaches over the columns `left..right`; Infinity when none does. */
export function topOver(segs: readonly Seg[], left: number, right: number): number {
  let top = Infinity;
  for (const seg of segs) {
    const ys = segYs(seg, left, right);
    if (ys && ys[0] < top) top = ys[0];
  }
  return top;
}

/** Two chips' rectangles overlap (with `gap` px between them kept free). */
export function overlaps(a: Rect, b: Rect, gap = 2): boolean {
  return a.left < b.right + gap && b.left < a.right + gap && a.top < b.bottom + gap && b.top < a.bottom + gap;
}

/** How far over (`above`) and under (`below`) the row `y` the nearest segment reaches over the columns `left..right`,
 * in pixels (0 when one runs through the row; Infinity when none is on that side). */
export function clearance(segs: readonly Seg[], left: number, right: number, y: number): { above: number; below: number } {
  let above = Infinity;
  let below = Infinity;
  for (const seg of segs) {
    const ys = segYs(seg, left, right);
    if (!ys) continue;
    if (ys[0] < y) above = Math.min(above, Math.max(0, y - ys[1]));
    if (ys[1] > y) below = Math.min(below, Math.max(0, ys[0] - y));
  }
  return { above, below };
}

/** The point of the rectangle's edge (or inside it) nearest `p`. */
export function nearestOn(r: Rect, p: Pt): Pt {
  return { x: Math.min(r.right, Math.max(r.left, p.x)), y: Math.min(r.bottom, Math.max(r.top, p.y)) };
}
