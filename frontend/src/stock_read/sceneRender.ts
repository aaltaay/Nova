/**
 * Drawing a stock-read scene on a chart pane (ADR 036), once `SetupShapesPrimitive` has mapped it to pixels:
 * the fills behind the candles (the levels' bands, the boxes), and over them the lines (the trend lines too), the
 * boxes' outlines, the
 * edge column (`edgeColumn.ts`: every word at the right edge), the +40% runs' arrows and every label --
 * the ones that stay put first, the boxes' and marks' taking the room around them (`sceneLabels.ts`). Nova's LULD
 * band on the 1-minute pane is `luldRender.ts`.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { IPrimitivePaneRenderer } from 'lightweight-charts';
import { EDGE_PRIORITY } from '../chart';
import { columnRects, drawColumn, layoutColumn, type ColumnItem, type ColumnReserve } from './edgeColumn';
import { foldColumnAt } from './levelFold';
import { drawLevels, fillLevelBands, type LevelPx, type TickPx } from './levelRender';
import { drawLuld, type LuldPx } from './luldRender';
import { fmtPx } from './planMath';
import type {
  SceneBox,
  SceneDot,
  SceneEdgeTag,
  SceneMark,
  ScenePath,
  ScenePin,
  SceneSegment,
  SceneTrend,
  SceneVLine,
  SceneWord,
} from './sceneTypes';
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
import { drawStrategy, type StrategyPx } from './strategyBoxRender';

/** A mark's arrow: its tip this far over the price, this tall and half this wide. */
const MARK_GAP_PX = 3;
const MARK_H = 6;
const MARK_HALF_W = 4;
/** A flat top's touch: a ring this wide on the candle's high, its label this far over it. */
export const RING_R_PX = 4;
const RING_LABEL_GAP_PX = 9;
/** A trend line's touch: a smaller ring on the line; its break, a cross this wide. */
export const TREND_RING_R_PX = 3;
const TREND_CROSS_PX = 4;

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
  dots: { x: number; y: number; d: SceneDot }[];
  /** The trend lines: each one's first touch, its last, and where it runs on the pane's newest candle. */
  trends: TrendPx[];
  /** Lines through points (an ABCD's swings), in pixels. */
  paths?: { pts: { x: number; y: number }[]; p: ScenePath }[];
  /** A setup's strategy box (`strategyBoxRender.ts`). */
  strategy?: StrategyPx | null;
  /** Nova's LULD band (`luldRender.ts`). */
  luld?: LuldPx | null;
}

export interface TrendPx {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  xe: number;
  ye: number;
  /** Its price on the newest candle. */
  pe: number;
  rings: { x: number; y: number }[];
  cross: { x: number; y: number } | null;
  tr: SceneTrend;
}

/** A label the last draw put on the pane, with its box's story: a mark alone is hovered too. */
export interface LabelHit {
  rect: LabelRect;
  hoverId: string;
}

export function emptyPx(): Px {
  return { boxes: [], segments: [], vlines: [], tags: [], pins: [], labels: 'compact', levels: [], ticks: [], words: [],
    reserves: [], topInset: 0, marks: [], dots: [], trends: [] };
}

/** A label that stays where it is: a level's, the focus line's, an edge tag, a flat top's touch count. */
interface FixedLabel {
  text: string;
  x: number;
  y: number;
  color: string;
  align: 'left' | 'right' | 'center';
}

type ColumnPx = Pick<Px, 'levels' | 'words' | 'tags'> & Partial<Pick<Px, 'trends'>>;

/** The column's words: each level's name, each line's tag, and a tag for every price out of view -- one word per price
 * (`levelFold.foldColumn`, 2026-10-13). */
export function columnItems(px: ColumnPx, height: number): ColumnItem[] {
  return columnOf(px, height).items;
}

/** The levels whose lines and bands the pane draws: every one but those folded into another line's word (operator
 * report 2026-10-13, "way too many lines": the $4.50 line a cent over target 2, VWAP's level under VWAP's own line). */
export function shownLevels(px: ColumnPx, height: number): LevelPx[] {
  const { folded } = columnOf(px, height);
  return folded.size === 0 ? px.levels : px.levels.filter(l => !folded.has(l));
}

/** A line through points, straight from each to the next (an ABCD's swings). */
function drawPath(ctx: CanvasRenderingContext2D, pts: { x: number; y: number }[], p: ScenePath): void {
  if (pts.length < 2) return;
  ctx.save();
  ctx.strokeStyle = p.color;
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.setLineDash(p.dashed ? [5, 4] : []);
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  for (const pt of pts.slice(1)) ctx.lineTo(pt.x, pt.y);
  ctx.stroke();
  ctx.restore();
}

function columnOf(px: ColumnPx, height: number): { items: ColumnItem[]; folded: Set<LevelPx> } {
  const items: ColumnItem[] = [];
  const from: (LevelPx | null)[] = [];
  for (const lp of px.levels) {
    const { y, l } = lp;
    if (!l.label) continue;
    from.push(lp);
    items.push({ y, text: l.label, color: l.color, style: 'plain', priority: l.priority ?? EDGE_PRIORITY.level,
      hoverId: l.hoverId, offText: null, price: l.price, span: { lo: l.lo, hi: l.hi }, foldName: l.foldName ?? null,
      absorbs: true });
  }
  // A trend line's name where it runs on the newest candle; out of view, a tag with that price.
  for (const { ye, pe, tr } of px.trends ?? []) {
    if (!tr.label) continue;
    items.push({ y: ye, text: tr.label, color: tr.labelColor, style: 'plain', priority: tr.priority, hoverId: tr.hoverId,
      offText: tr.offTag === false ? null : `${tr.label} ${fmtPx(pe)}`, price: pe, foldName: tr.foldName });
  }
  for (const { y, value, w } of px.words) {
    items.push({ y, text: w.text, color: w.color, style: w.style ?? 'filled', priority: w.priority, hoverId: null,
      offText: w.valueWhenOff ? `${w.text} ${fmtPx(value)}` : w.text, price: value, absorbs: w.absorbs ?? false });
  }
  const named = new Set(px.words.map(w => w.w.id));
  for (const { y, t } of px.tags) {
    // A tag says where a price out of view is; in view its line (and label, when it has one) says it.
    if ((t.id && named.has(t.id)) || (y >= 0 && y <= height)) continue;
    items.push({ y, text: t.label, color: t.color, style: 'plain', priority: EDGE_PRIORITY.offView, hoverId: null,
      offText: t.label });
  }
  while (from.length < items.length) from.push(null);
  const { items: out, gone } = foldColumnAt(items, height);
  const folded = new Set<LevelPx>();
  for (const i of gone) {
    const lp = from[i];
    if (lp) folded.add(lp);
  }
  return { items: out, folded };
}

/** A mark's arrow over its candle's high: pointing down at it (a run), or up from it (a flat top's break). */
function drawMarkArrow(ctx: CanvasRenderingContext2D, x: number, y: number, color: string, dir: 'up' | 'down' = 'down'): void {
  const near = y - MARK_GAP_PX;
  const far = near - MARK_H;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(x, dir === 'down' ? near : far);
  ctx.lineTo(x - MARK_HALF_W, dir === 'down' ? far : near);
  ctx.lineTo(x + MARK_HALF_W, dir === 'down' ? far : near);
  ctx.closePath();
  ctx.fill();
}

/** A trend line: solid from its first touch to its last (dashed when it broke), dashed on to the newest candle;
 * a ring on each touch and a cross on the candle that closed through it. */
function drawTrend(ctx: CanvasRenderingContext2D, t: TrendPx): void {
  const { tr } = t;
  ctx.strokeStyle = tr.color;
  ctx.lineWidth = tr.faded ? 1 : 1.5;
  ctx.setLineDash(tr.faded ? [4, 3] : []);
  ctx.beginPath();
  ctx.moveTo(t.x1, t.y1);
  ctx.lineTo(t.x2, t.y2);
  ctx.stroke();
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  ctx.moveTo(t.x2, t.y2);
  ctx.lineTo(t.xe, t.ye);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.lineWidth = 1.25;
  for (const r of t.rings) {
    ctx.beginPath();
    ctx.arc(r.x, r.y, TREND_RING_R_PX, 0, 2 * Math.PI);
    ctx.stroke();
  }
  if (t.cross) {
    const { x, y } = t.cross;
    ctx.beginPath();
    ctx.moveTo(x - TREND_CROSS_PX, y - TREND_CROSS_PX);
    ctx.lineTo(x + TREND_CROSS_PX, y + TREND_CROSS_PX);
    ctx.moveTo(x - TREND_CROSS_PX, y + TREND_CROSS_PX);
    ctx.lineTo(x + TREND_CROSS_PX, y - TREND_CROSS_PX);
    ctx.stroke();
  }
  ctx.lineWidth = 1;
}

/** How far a point is from the segment (x1, y1)-(x2, y2), in pixels. */
export function segmentDistance(x: number, y: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  const k = len2 > 0 ? Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / len2)) : 0;
  return Math.hypot(x - (x1 + k * dx), y - (y1 + k * dy));
}

/** A flat top's touch: a filled ring on the candle's high. */
function drawRing(ctx: CanvasRenderingContext2D, x: number, y: number, d: SceneDot): void {
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.arc(x, y, RING_R_PX, 0, 2 * Math.PI);
  ctx.fillStyle = d.fill;
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = d.color;
  ctx.stroke();
  ctx.lineWidth = 1;
}

export class FillRenderer implements IPrimitivePaneRenderer {
  private readonly px: Px;

  constructor(px: Px) {
    this.px = px;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      fillLevelBands(ctx, shownLevels(this.px, mediaSize.height), mediaSize.width);
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
  private readonly onWords: (rects: LabelRect[]) => void;

  constructor(px: Px, onLabels: (hits: LabelHit[]) => void, onWords: (rects: LabelRect[]) => void = () => {}) {
    this.px = px;
    this.onLabels = onLabels;
    this.onWords = onWords;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const width = mediaSize.width;
      const height = mediaSize.height;
      const measure = labelMeasure(ctx);
      const tickHits = drawLevels(ctx, shownLevels(this.px, height), this.px.ticks, width, height);
      for (const t of this.px.trends ?? []) drawTrend(ctx, t);
      for (const path of this.px.paths ?? []) drawPath(ctx, path.pts, path.p);
      if (this.px.luld) drawLuld(ctx, this.px.luld);
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
      for (const { x, y, m } of this.px.marks) drawMarkArrow(ctx, x, y, m.color, m.dir);
      for (const { x, y, d } of this.px.dots) {
        drawRing(ctx, x, y, d);
        if (d.label) {
          const gap = RING_R_PX + RING_LABEL_GAP_PX;
          fixed.push({ text: d.label, x, y: d.labelBelow ? y + gap : y - gap, color: d.labelColor ?? d.color,
            align: 'center' });
        }
      }
      // Every word at the right edge in one column; the boxes' labels take the room around it. A setup's strategy box
      // goes under the column, its own words clear of the column's.
      const items = columnItems(this.px, height);
      const layout = layoutColumn(items, height, this.px.topInset, this.px.reserves);
      const boxWords = this.px.strategy
        ? drawStrategy(ctx, this.px.strategy, width, columnRects(layout, width, measure), height) : [];
      const column = drawColumn(ctx, items, layout, width, measure);
      const levelHits = [...tickHits, ...column.hits];
      const obstacles: LabelRect[] = [...tickHits.map(h => h.rect), ...column.rects, ...boxWords];
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
        const forms = labelForms(m.label, m.shrink, this.px.labels);
        if (forms.length === 0) continue;
        asks.push({ forms, x, y: y - MARK_GAP_PX - MARK_H - 2 - LABEL_H / 2, fixed: false, rank: m.rank, center: true });
        owners.push({ color: m.color, hoverId: m.hoverId });
      }
      const hits: LabelHit[] = [];
      const words: LabelRect[] = [...obstacles];
      for (const l of placeLabels(asks, measure, width, obstacles)) {
        const o = owners[l.ask];
        drawLabel(ctx, l.text, l.left, l.y, l.width, o.color);
        const rect = labelRect(l.left, l.y, l.width, 'left', 0);
        words.push(rect);
        if (o.hoverId) hits.push({ rect, hoverId: o.hoverId });
      }
      this.onLabels([...hits, ...levelHits]);
      // Every word on the pane, for what floats over a candle (the close countdown) to keep clear of.
      this.onWords(words);
      for (const { f, r, w } of fixedDrawn) drawLabel(ctx, f.text, r.left, f.y, w, f.color);
      for (const { x, y, p, r } of pins) drawPin(ctx, x, y, p, r);
    });
  }
}
