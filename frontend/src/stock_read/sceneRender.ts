/**
 * Drawing a stock-read scene on a chart pane (ADR 036), once `SetupShapesPrimitive` has mapped it to pixels:
 * the fills behind the candles (the levels' bands, the boxes), and over them the lines, the boxes' outlines, the
 * edge column (`edgeColumn.ts`: every word at the right edge), the +40% runs' arrows and every label --
 * the ones that stay put first, the boxes' and marks' taking the room around them (`sceneLabels.ts`).
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';
import { EDGE_PRIORITY } from '../chart';
import { drawColumn, layoutColumn, type ColumnItem, type ColumnReserve } from './edgeColumn';
import { drawLevels, fillLevelBands, type LevelPx, type TickPx } from './levelRender';
import { fmtPx } from './planMath';
import type { SceneBox, SceneEdgeTag, SceneMark, ScenePin, SceneSegment, SceneVLine, SceneWord } from './sceneTypes';
import {
  drawLabel,
  drawPin,
  LABEL_H,
  labelForms,
  labelMeasure,
  labelRect,
  pinRect,
  placeLabels,
  type LabelAsk,
  type LabelDetail,
  type LabelRect,
} from './sceneLabels';

/** A mark's arrow: its tip this far over the price, this tall and half this wide. */
const MARK_GAP_PX = 3;
const MARK_H = 6;
const MARK_HALF_W = 4;

export interface Px {
  boxes: { x1: number; x2: number | null; y1: number; y2: number; b: SceneBox }[];
  segments: { x1: number | null; y: number; s: SceneSegment }[];
  vlines: { x: number; v: SceneVLine }[];
  tags: { y: number; t: SceneEdgeTag }[];
  pins: { x: number; y: number; p: ScenePin }[];
  labels: LabelDetail;
  levels: LevelPx[];
  ticks: TickPx[];
  words: { y: number; value: number; w: SceneWord }[];
  reserves: ColumnReserve[];
  topInset: number;
  marks: { x: number; y: number; m: SceneMark }[];
}

/** A label the last draw put on the pane, with its box's story: a mark alone is hovered too. */
export interface LabelHit {
  rect: LabelRect;
  hoverId: string;
}

export function emptyPx(): Px {
  return { boxes: [], segments: [], vlines: [], tags: [], pins: [], labels: 'compact', levels: [], ticks: [], words: [],
    reserves: [], topInset: 0, marks: [] };
}

/** A label that stays where it is: a level's, the focus line's, an edge tag. */
interface FixedLabel {
  text: string;
  x: number;
  y: number;
  color: string;
  align: 'left' | 'right';
}

/** The column's words: each level's name, each line's tag, and a tag for every price out of view. */
export function columnItems(px: Pick<Px, 'levels' | 'words' | 'tags'>, height: number): ColumnItem[] {
  const items: ColumnItem[] = [];
  for (const { y, l } of px.levels) {
    if (!l.label) continue;
    items.push({ y, text: l.label, color: l.color, style: 'plain', priority: l.priority ?? EDGE_PRIORITY.level,
      hoverId: l.hoverId, offText: null });
  }
  for (const { y, value, w } of px.words) {
    items.push({ y, text: w.text, color: w.color, style: 'filled', priority: w.priority, hoverId: null,
      offText: w.valueWhenOff ? `${w.text} ${fmtPx(value)}` : w.text });
  }
  const named = new Set(px.words.map(w => w.w.id));
  for (const { y, t } of px.tags) {
    // A tag says where a price out of view is; in view its line (and label, when it has one) says it.
    if ((t.id && named.has(t.id)) || (y >= 0 && y <= height)) continue;
    items.push({ y, text: t.label, color: t.color, style: 'plain', priority: EDGE_PRIORITY.offView, hoverId: null,
      offText: t.label });
  }
  return items;
}

/** A mark's arrow, pointing down at its candle's high. */
function drawMarkArrow(ctx: CanvasRenderingContext2D, x: number, y: number, color: string): void {
  const tip = y - MARK_GAP_PX;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(x, tip);
  ctx.lineTo(x - MARK_HALF_W, tip - MARK_H);
  ctx.lineTo(x + MARK_HALF_W, tip - MARK_H);
  ctx.closePath();
  ctx.fill();
}

export class FillRenderer implements IPrimitivePaneRenderer {
  private readonly px: Px;

  constructor(px: Px) {
    this.px = px;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      fillLevelBands(ctx, this.px.levels, mediaSize.width);
      for (const { x1, x2, y1, y2, b } of this.px.boxes) {
        const right = x2 ?? mediaSize.width;
        const top = Math.min(y1, y2);
        const h = Math.max(1, Math.abs(y2 - y1));
        ctx.fillStyle = b.fill;
        ctx.fillRect(x1, top, Math.max(1, right - x1), h);
      }
    });
  }
}

export class LineRenderer implements IPrimitivePaneRenderer {
  private readonly px: Px;
  private readonly onLabels: (hits: LabelHit[]) => void;

  constructor(px: Px, onLabels: (hits: LabelHit[]) => void) {
    this.px = px;
    this.onLabels = onLabels;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const width = mediaSize.width;
      const height = mediaSize.height;
      const measure = labelMeasure(ctx);
      const tickHits = drawLevels(ctx, this.px.levels, this.px.ticks, width, height);
      ctx.lineWidth = 1;
      for (const { x1, x2, y1, y2, b } of this.px.boxes) {
        if (!b.stroke) continue;
        const right = x2 ?? width;
        ctx.strokeStyle = b.stroke;
        ctx.setLineDash(b.dashed ? [4, 3] : []);
        ctx.strokeRect(Math.round(x1) + 0.5, Math.round(Math.min(y1, y2)) + 0.5, Math.max(1, right - x1),
          Math.max(1, Math.abs(y2 - y1)));
      }
      const fixed: FixedLabel[] = [];
      for (const { x1, y, s } of this.px.segments) {
        const left = x1 ?? 0;
        ctx.strokeStyle = s.color;
        ctx.setLineDash(s.dashed ? [3, 3] : []);
        ctx.beginPath();
        ctx.moveTo(left, Math.round(y) + 0.5);
        ctx.lineTo(width, Math.round(y) + 0.5);
        ctx.stroke();
        if (s.label) fixed.push({ text: s.label, x: left + 4, y: y - 8, color: s.color, align: 'left' });
      }
      ctx.setLineDash([2, 3]);
      for (const { x, v } of this.px.vlines) {
        ctx.strokeStyle = v.color;
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, 0);
        ctx.lineTo(Math.round(x) + 0.5, mediaSize.height);
        ctx.stroke();
        if (v.label) {
          const right = x > width * 0.6;
          fixed.push({ text: v.label, x: right ? x - 4 : x + 4, y: mediaSize.height - 12, color: v.color,
            align: right ? 'right' : 'left' });
        }
      }
      ctx.setLineDash([]);
      for (const { x, y, m } of this.px.marks) drawMarkArrow(ctx, x, y, m.color);
      // Every word at the right edge in one column; the boxes' labels take the room around it.
      const items = columnItems(this.px, height);
      const column = drawColumn(ctx, items, layoutColumn(items, height, this.px.topInset, this.px.reserves), width,
        measure);
      const levelHits = [...tickHits, ...column.hits];
      const obstacles: LabelRect[] = [...tickHits.map(h => h.rect), ...column.rects];
      const fixedDrawn = fixed.map(f => {
        const w = measure(f.text);
        const r = labelRect(f.x, f.y, w, f.align, width);
        obstacles.push(r);
        return { f, r, w };
      });
      const pins = this.px.pins.map(({ x, y, p }) => {
        const r = pinRect(ctx, x, y, p.label, width);
        obstacles.push(r);
        return { x, y, p, r };
      });
      const asks: LabelAsk[] = [];
      const owners: { color: string; hoverId?: string }[] = [];
      for (const { x1, x2, y1, y2, b } of this.px.boxes) {
        const right = x2 ?? width;
        if (!b.label || right < 0 || x1 > width) continue; // a box out of view says nothing
        const forms = labelForms(b.label, b.shrink, this.px.labels);
        if (forms.length === 0) continue;
        asks.push({ forms, x: x1, y: b.labelBelow ? Math.max(y1, y2) + 9 : Math.min(y1, y2) - 9, fixed: !b.shrink,
          rank: b.shrink?.rank ?? 0 });
        owners.push({ color: b.labelColor, hoverId: b.hoverId });
      }
      for (const { x, y, m } of this.px.marks) {
        if (x < 0 || x > width) continue;
        asks.push({ forms: [m.label], x, y: y - MARK_GAP_PX - MARK_H - 2 - LABEL_H / 2, fixed: false, rank: m.rank,
          center: true });
        owners.push({ color: m.color });
      }
      const hits: LabelHit[] = [];
      for (const l of placeLabels(asks, measure, width, obstacles)) {
        const o = owners[l.ask];
        drawLabel(ctx, l.text, l.left, l.y, l.width, o.color);
        if (o.hoverId) hits.push({ rect: labelRect(l.left, l.y, l.width, 'left', 0), hoverId: o.hoverId });
      }
      this.onLabels([...hits, ...levelHits]);
      for (const { f, r, w } of fixedDrawn) drawLabel(ctx, f.text, r.left, f.y, w, f.color);
      for (const { x, y, p, r } of pins) drawPin(ctx, x, y, p, r);
    });
  }
}
