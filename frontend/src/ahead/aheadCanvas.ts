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
  nowBg: AHEAD_COLORS.nowBg,
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
const CHIP_H = 18;
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

/**
 * Words on a rounded chip. `anchor` says which edge `x` is: 'end' puts the chip's right edge there. `y` is the chip's
 * vertical centre. Returns the rectangle it holds (for the pane's words), or null when it would not fit the pane.
 */
export function chip(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, fg: string, bg: string,
  anchor: 'start' | 'end', bounds: { width: number; height: number }): Rect | null {
  ctx.save();
  ctx.font = CHIP_FONT;
  const w = ctx.measureText(text).width + 2 * CHIP_PAD_PX;
  const left = anchor === 'end' ? x - w : x;
  const top = y - CHIP_H / 2;
  if (left < 0 || top < 0 || left + w > bounds.width || top + CHIP_H > bounds.height) {
    ctx.restore();
    return null;
  }
  ctx.fillStyle = bg;
  ctx.beginPath();
  if (typeof ctx.roundRect === 'function') ctx.roundRect(left, top, w, CHIP_H, CHIP_RADIUS_PX);
  else ctx.rect(left, top, w, CHIP_H);
  ctx.fill();
  ctx.fillStyle = fg;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, left + CHIP_PAD_PX, y + 0.5);
  ctx.restore();
  return { left, top, right: left + w, bottom: top + CHIP_H };
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

/** Two chips' rectangles overlap (with `gap` px between them kept free). */
export function overlaps(a: Rect, b: Rect, gap = 2): boolean {
  return a.left < b.right + gap && b.left < a.right + gap && a.top < b.bottom + gap && b.top < a.bottom + gap;
}
