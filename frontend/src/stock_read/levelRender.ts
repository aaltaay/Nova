/**
 * The day's levels on a chart pane (ADR 036 amendment 2026-09-30), drawn by `SetupShapesPrimitive`: a
 * zone's band behind the candles, its line across the pane, its label at the right edge (labels close
 * together stack down so none covers another), and a short tick on the price axis for every zone the
 * pane lists without a line. A label and a tick are hover targets: they name the zone's card.
 */
import { drawLabel, LABEL_H, type LabelRect } from './sceneLabels';

export interface SceneLevel {
  lo: number;
  hi: number;
  /** The zone's edge nearest the price: where its line and label go. */
  price: number;
  color: string;
  /** Canvas dash pattern; empty is solid. */
  dash: number[];
  width: number;
  /** The label at the right edge; null draws the line alone. */
  label: string | null;
  hoverId: string | null;
}

export interface SceneTick {
  price: number;
  color: string;
  hoverId: string | null;
}

export interface LevelPx {
  y: number;
  y1: number;
  y2: number;
  l: SceneLevel;
}

export interface TickPx {
  y: number;
  t: SceneTick;
}

export interface LevelHit {
  rect: LabelRect;
  hoverId: string;
}

/** A band this tall or more is filled; thinner zones are their line alone. */
const BAND_MIN_PX = 2;
const BAND_ALPHA = 0.1;
const EDGE_PX = 4;
const TICK_PX = 9;
/** The hover target around a tick, in pixels either side of it. */
const TICK_HIT_PX = 4;
/** A label takes at most this share of the pane's width; longer ones drop their last reasons. */
const LABEL_MAX_SHARE = 0.6;

/** `#rrggbb` at `alpha`; anything else is returned as it is. */
export function alpha(color: string, a: number): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color);
  if (!m) return color;
  return `rgba(${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}, ${a})`;
}

export function fillLevelBands(ctx: CanvasRenderingContext2D, levels: LevelPx[], width: number): void {
  for (const { y1, y2, l } of levels) {
    const h = Math.abs(y2 - y1);
    if (h < BAND_MIN_PX) continue;
    ctx.fillStyle = alpha(l.color, BAND_ALPHA);
    ctx.fillRect(0, Math.min(y1, y2), width, h);
  }
}

/** `text` cut at its last whole " · " part (else its characters, with an ellipsis) to fit `maxW`. */
export function fitText(text: string, maxW: number, measure: (t: string) => number): string {
  if (measure(text) <= maxW) return text;
  const parts = text.split(' · ');
  while (parts.length > 1) {
    parts.pop();
    const cut = `${parts.join(' · ')} …`;
    if (measure(cut) <= maxW) return cut;
  }
  let head = parts[0];
  while (head.length > 1 && measure(`${head}…`) > maxW) head = head.slice(0, -1);
  return `${head}…`;
}

/** Lines, labels and ticks; returns the labels' and ticks' hover targets. */
export function drawLevels(
  ctx: CanvasRenderingContext2D,
  levels: LevelPx[],
  ticks: TickPx[],
  width: number,
  height: number,
  measure: (text: string) => number,
): LevelHit[] {
  const hits: LevelHit[] = [];
  for (const { y, l } of levels) {
    ctx.strokeStyle = l.color;
    ctx.lineWidth = l.width;
    ctx.setLineDash(l.dash);
    ctx.beginPath();
    ctx.moveTo(0, Math.round(y) + 0.5);
    ctx.lineTo(width, Math.round(y) + 0.5);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.lineWidth = 2;
  for (const { y, t } of ticks) {
    if (y < 0 || y > height) continue;
    ctx.strokeStyle = t.color;
    ctx.beginPath();
    ctx.moveTo(width - TICK_PX, Math.round(y) + 0.5);
    ctx.lineTo(width, Math.round(y) + 0.5);
    ctx.stroke();
    if (t.hoverId) {
      hits.push({ rect: { left: width - TICK_PX - TICK_HIT_PX, right: width, top: y - TICK_HIT_PX, bottom: y + TICK_HIT_PX },
        hoverId: t.hoverId });
    }
  }
  ctx.lineWidth = 1;
  const shown = levels.filter(p => p.l.label && p.y >= 0 && p.y <= height).sort((a, b) => a.y - b.y);
  const ys = stackLabels(shown.map(p => p.y), height);
  shown.forEach(({ l }, i) => {
    const at = ys[i];
    if (at === null) return;
    const text = fitText(l.label as string, width * LABEL_MAX_SHARE, measure);
    const w = measure(text);
    const left = width - EDGE_PX - TICK_PX - w;
    drawLabel(ctx, text, left, at, w, l.color);
    if (l.hoverId) hits.push({ rect: { left, right: left + w, top: at - LABEL_H / 2, bottom: at + LABEL_H / 2 }, hoverId: l.hoverId });
  });
  return hits;
}

/** Where each label goes, top to bottom: at its line, moved down under the one above it, then the stack
 * pushed back up where it would run past the pane's bottom. A label with no room even then is null. */
export function stackLabels(ys: number[], height: number): (number | null)[] {
  const step = LABEL_H + 1;
  const top = LABEL_H / 2;
  const bottom = height - LABEL_H / 2;
  const out = ys.map(y => Math.min(Math.max(y, top), bottom));
  for (let i = 1; i < out.length; i += 1) out[i] = Math.max(out[i], out[i - 1] + step);
  if (out.length && out[out.length - 1] > bottom) {
    out[out.length - 1] = bottom;
    for (let i = out.length - 2; i >= 0; i -= 1) out[i] = Math.min(out[i], out[i + 1] - step);
  }
  return out.map(y => (y < top ? null : y));
}
