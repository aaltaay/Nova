/**
 * The day's levels on a chart pane (ADR 036 amendment 2026-09-30), drawn by `SetupShapesPrimitive`: a
 * zone's band behind the candles, its line across the pane, and a short tick on the price axis for every
 * zone the pane lists without a line. Its label goes in the pane's edge column with every other word at the
 * right edge (`edgeColumn.ts`), so none covers another. A label and a tick are hover targets: they name the
 * zone's card.
 */
import type { LabelRect } from './sceneLabels';

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
  /** How firmly its label keeps its place in a crowded column (`EDGE_PRIORITY`); a level's by default. */
  priority?: number;
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
const TICK_PX = 9;
/** The hover target around a tick, in pixels either side of it. */
const TICK_HIT_PX = 4;

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

/** Lines and ticks; returns the ticks' hover targets. A level's label is the edge column's (`edgeColumn.ts`). */
export function drawLevels(
  ctx: CanvasRenderingContext2D,
  levels: LevelPx[],
  ticks: TickPx[],
  width: number,
  height: number,
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
  return hits;
}
