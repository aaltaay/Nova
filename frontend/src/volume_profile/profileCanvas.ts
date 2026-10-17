/**
 * The volume profile's canvas drawing (ADR 058), in the pane's CSS pixels: the title tabs, the level names and lines,
 * the notes, and a histogram with the white outline that traces its shape. `VolumeProfilePrimitive` works out where
 * everything sits from the chart's prices and times; this file only draws it.
 */
import type { VolumeProfile } from './volumeProfile';
import { VP_COLORS, VP_LABEL_FONT, VP_OUTLINE_SMOOTH_ROWS, VP_TAG_FONT } from './volumeProfileConstants';

export interface ProfileLayer {
  profile: VolumeProfile;
  /** Chart seconds (ET wall clock read as UTC) where the measured stretch starts and ends. */
  start: number;
  end: number;
  title: string;
}

export interface HandleRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** One profile placed on the pane: its box's left and end x, its prices' y, and each row's top and bottom. */
export interface LayerGeometry {
  layer: ProfileLayer;
  left: number;
  end: number;
  yHigh: number;
  yLow: number;
  yPoc: number;
  yVah: number;
  yVal: number;
  rowTop: number[];
  rowBottom: number[];
}

function smoothed(rows: number[], k: number): number[] {
  return rows.map((_, i) => {
    let sum = 0;
    let n = 0;
    for (let j = Math.max(0, i - k); j <= Math.min(rows.length - 1, i + k); j += 1) {
      sum += rows[j];
      n += 1;
    }
    return sum / n;
  });
}

export function tag(
  ctx: CanvasRenderingContext2D, text: string, x: number, y: number, align: 'left' | 'right' | 'center', bg: string,
): HandleRect {
  ctx.font = VP_TAG_FONT;
  const w = ctx.measureText(text).width + 12;
  const h = 15;
  const left = align === 'left' ? x : align === 'right' ? x - w : x - w / 2;
  ctx.fillStyle = bg;
  ctx.beginPath();
  ctx.roundRect(left, y, w, h, 3);
  ctx.fill();
  ctx.fillStyle = VP_COLORS.label;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillText(text, left + 6, y + h / 2 + 0.5);
  return { x: left, y, w, h };
}

export function hLine(
  ctx: CanvasRenderingContext2D, y: number, x0: number, x1: number, color: string, width: number, dash: number[] = [],
): void {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.beginPath();
  ctx.moveTo(x0, Math.round(y) + 0.5);
  ctx.lineTo(x1, Math.round(y) + 0.5);
  ctx.stroke();
  ctx.setLineDash([]);
}

/** A level's name at the start of its line, on a backing so a candle never covers it. */
export function levelName(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, color: string): void {
  ctx.font = VP_LABEL_FONT;
  const w = ctx.measureText(text).width;
  ctx.fillStyle = VP_COLORS.labelBacking;
  ctx.beginPath();
  ctx.roundRect(x - 3, y - 14, w + 6, 12, 2);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  ctx.fillText(text, x, y - 3);
}

/** A note ending at `right`, `y` its top: why a profile is not drawn. */
export function note(ctx: CanvasRenderingContext2D, text: string, right: number, y: number): void {
  ctx.font = VP_TAG_FONT;
  const w = ctx.measureText(text).width + 10;
  ctx.fillStyle = VP_COLORS.labelBacking;
  ctx.fillRect(right - w, y, w, 14);
  ctx.fillStyle = VP_COLORS.yesterday;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, right - w + 5, y + 7.5);
}

/** One histogram: rows grow from `base` toward `dir` (-1 left, +1 right), up volume next to the base. */
export function histogram(
  ctx: CanvasRenderingContext2D, g: LayerGeometry, base: number, dir: 1 | -1, width: number, alphaIn: number,
  alphaOut: number,
): void {
  const p = g.layer.profile;
  const totals = p.up.map((u, i) => u + p.down[i]);
  const max = Math.max(...totals);
  if (max <= 0) return;
  for (let i = 0; i < totals.length; i += 1) {
    const top = g.rowTop[i];
    const h = Math.max(1, g.rowBottom[i] - top);
    const wUp = (p.up[i] / max) * width;
    const wDown = (p.down[i] / max) * width;
    ctx.globalAlpha = i >= p.valRow && i <= p.vahRow ? alphaIn : alphaOut;
    ctx.fillStyle = VP_COLORS.up;
    ctx.fillRect(dir < 0 ? base - wUp : base, top, wUp, h);
    ctx.fillStyle = VP_COLORS.down;
    ctx.fillRect(dir < 0 ? base - wUp - wDown : base + wUp, top, wDown, h);
  }
  ctx.globalAlpha = 1;
  const s = smoothed(totals, VP_OUTLINE_SMOOTH_ROWS);
  ctx.strokeStyle = VP_COLORS.outline;
  ctx.lineWidth = 1;
  ctx.beginPath();
  s.forEach((v, i) => {
    const x = base + dir * (v / max) * width;
    const y = (g.rowTop[i] + g.rowBottom[i]) / 2;
    if (i === 0) ctx.moveTo(x, g.rowBottom[i]);
    ctx.lineTo(x, y);
  });
  ctx.lineTo(base + dir * (s[s.length - 1] / max) * width, g.rowTop[s.length - 1]);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
  ctx.beginPath();
  ctx.moveTo(base, g.yHigh);
  ctx.lineTo(base, g.yLow);
  ctx.stroke();
}
