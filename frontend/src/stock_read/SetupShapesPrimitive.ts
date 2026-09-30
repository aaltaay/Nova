/**
 * Lightweight-charts series primitive for the stock read (ADR 036): the setups' boxes (leg, pole,
 * pullback, flag, base, red phase), the plan's risk and reward zones, level segments, a focus line
 * for a decision the operator asked to see, edge tags for levels above or below the visible
 * prices, and the moment's pin (ENTER NOW, SELL NOW, what Nova did: ADR 037) on its candle. It draws a scene it is given; `chartShapes.ts` decides what the scene holds and
 * `StockReadChartLayer` maps its times onto this pane's bars. A box with a `hoverId` is reported to the
 * chart as hovered (`hitTest`) -- over the box, or over the label it drew for the box -- so the pane can
 * tell that setup's story under the pointer; a level's label or axis tick names the level's card. Where each label goes, and how much a past setup's says, is
 * `sceneLabels.ts`.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  AutoscaleInfo,
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  PrimitiveHoveredItem,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';
import { drawLevels, fillLevelBands, type LevelPx, type SceneLevel, type SceneTick, type TickPx } from './levelRender';
import {
  drawLabel,
  drawPin,
  labelForms,
  labelMeasure,
  labelRect,
  pinRect,
  placeLabels,
  type LabelAsk,
  type LabelDetail,
  type LabelRect,
  type LabelShrink,
} from './sceneLabels';

/** A pointer this close to a box's edge still hovers it. */
const HIT_SLACK_PX = 2;

export interface SceneBox {
  t1: Time;
  /** Null runs to the pane's right edge. */
  t2: Time | null;
  p1: number;
  p2: number;
  fill: string;
  stroke: string | null;
  dashed: boolean;
  label: string | null;
  labelColor: string;
  /** The label under the box (a consolidation's), so it never sits on its leg's. */
  labelBelow?: boolean;
  /** A label that makes room (a past setup's): its shorter forms and its claim to the room. Without it
   * the label is drawn whole where it is (a live lane's). */
  shrink?: LabelShrink;
  /** What the pane reports as hovered over this box (`hitTest`): a lane's or a past setup's story. */
  hoverId?: string;
}

export interface SceneSegment {
  /** Null starts at the pane's left edge. */
  t1: Time | null;
  price: number;
  color: string;
  dashed: boolean;
  label: string | null;
}

export interface SceneVLine {
  t: Time;
  color: string;
  label: string | null;
}

export interface SceneEdgeTag {
  price: number;
  label: string;
  color: string;
}

/** A filled tag over a price on one candle, on a stem down to the price. */
export interface ScenePin {
  t: Time;
  price: number;
  label: string;
  color: string;
}

export interface Scene {
  boxes: SceneBox[];
  segments: SceneSegment[];
  vlines: SceneVLine[];
  edgeTags: SceneEdgeTag[];
  pins: ScenePin[];
  /** Prices the pane's autoscale must keep in view (the plan's stop and target). */
  keepInView: { min: number; max: number } | null;
  /** How much a past setup's label says. */
  labels: LabelDetail;
  /** The day's levels with a line, and the rest as ticks on the price axis (`levelRender.ts`). */
  levels?: SceneLevel[];
  ticks?: SceneTick[];
}

export const EMPTY_SCENE: Scene = {
  boxes: [], segments: [], vlines: [], edgeTags: [], pins: [], keepInView: null, labels: 'compact',
};

const TAG_TOP = 26;
const TAG_H = 15;

interface Px {
  boxes: { x1: number; x2: number | null; y1: number; y2: number; b: SceneBox }[];
  segments: { x1: number | null; y: number; s: SceneSegment }[];
  vlines: { x: number; v: SceneVLine }[];
  tags: { y: number; t: SceneEdgeTag }[];
  pins: { x: number; y: number; p: ScenePin }[];
  labels: LabelDetail;
  levels: LevelPx[];
  ticks: TickPx[];
}

/** A label the last draw put on the pane, with its box's story: a mark alone is hovered too. */
export interface LabelHit {
  rect: LabelRect;
  hoverId: string;
}

function emptyPx(): Px {
  return { boxes: [], segments: [], vlines: [], tags: [], pins: [], labels: 'compact', levels: [], ticks: [] };
}

/** A label that stays where it is: a level's, the focus line's, an edge tag. */
interface FixedLabel {
  text: string;
  x: number;
  y: number;
  color: string;
  align: 'left' | 'right';
}

class FillRenderer implements IPrimitivePaneRenderer {
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

class LineRenderer implements IPrimitivePaneRenderer {
  private readonly px: Px;
  private readonly onLabels: (hits: LabelHit[]) => void;

  constructor(px: Px, onLabels: (hits: LabelHit[]) => void) {
    this.px = px;
    this.onLabels = onLabels;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const width = mediaSize.width;
      const measure = labelMeasure(ctx);
      const levelHits = drawLevels(ctx, this.px.levels, this.px.ticks, width, mediaSize.height, measure);
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
      let up = 0;
      let down = 0;
      for (const { y, t } of this.px.tags) {
        if (y < 0) {
          fixed.push({ text: `↑ ${t.label}`, x: width - 6, y: TAG_TOP + up * TAG_H, color: t.color, align: 'right' });
          up += 1;
        } else if (y > mediaSize.height) {
          fixed.push({ text: `↓ ${t.label}`, x: width - 6, y: mediaSize.height - 10 - down * TAG_H, color: t.color,
            align: 'right' });
          down += 1;
        }
      }
      // The words that stay put are placed first; the boxes' labels take the room around them.
      const obstacles: LabelRect[] = levelHits.map(h => h.rect);
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
      const owners: SceneBox[] = [];
      for (const { x1, x2, y1, y2, b } of this.px.boxes) {
        const right = x2 ?? width;
        if (!b.label || right < 0 || x1 > width) continue; // a box out of view says nothing
        const forms = labelForms(b.label, b.shrink, this.px.labels);
        if (forms.length === 0) continue;
        asks.push({ forms, x: x1, y: b.labelBelow ? Math.max(y1, y2) + 9 : Math.min(y1, y2) - 9, fixed: !b.shrink,
          rank: b.shrink?.rank ?? 0 });
        owners.push(b);
      }
      const hits: LabelHit[] = [];
      for (const l of placeLabels(asks, measure, width, obstacles)) {
        const b = owners[l.ask];
        drawLabel(ctx, l.text, l.left, l.y, l.width, b.labelColor);
        if (b.hoverId) hits.push({ rect: labelRect(l.left, l.y, l.width, 'left', 0), hoverId: b.hoverId });
      }
      this.onLabels([...hits, ...levelHits]);
      for (const { f, r, w } of fixedDrawn) drawLabel(ctx, f.text, r.left, f.y, w, f.color);
      for (const { x, y, p, r } of pins) drawPin(ctx, x, y, p, r);
    });
  }
}

class View implements IPrimitivePaneView {
  private readonly source: SetupShapesPrimitive;
  private readonly layer: 'fill' | 'lines';

  constructor(source: SetupShapesPrimitive, layer: 'fill' | 'lines') {
    this.source = source;
    this.layer = layer;
  }

  renderer(): IPrimitivePaneRenderer {
    if (this.layer === 'fill') return new FillRenderer(this.source.px);
    return new LineRenderer(this.source.px, hits => {
      this.source.labelHits = hits;
    });
  }

  zOrder(): PrimitivePaneViewZOrder {
    return this.layer === 'fill' ? 'bottom' : 'top';
  }
}

export class SetupShapesPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private scene: Scene = EMPTY_SCENE;
  private readonly views = [new View(this, 'fill'), new View(this, 'lines')];
  px: Px = emptyPx();
  /** Where the last draw put the boxes' labels, kept apart from `px`: `updateAllViews` rebuilds that
   * without drawing, and the labels on screen are the last draw's. */
  labelHits: LabelHit[] = [];

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
    this.requestUpdate();
  }

  detached(): void {
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
    this.labelHits = [];
  }

  setScene(scene: Scene): void {
    this.scene = scene;
    this.requestUpdate?.();
  }

  updateAllViews(): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) {
      this.px = emptyPx();
      return;
    }
    const ts = chart.timeScale();
    const x = (t: Time | null) => (t === null ? null : ts.timeToCoordinate(t));
    const y = (p: number) => series.priceToCoordinate(p);
    // A box covers its first and last candles whole; a zone to the right edge starts after its candle.
    const half = (ts.options().barSpacing || 6) / 2;
    const boxes: Px['boxes'] = [];
    for (const b of this.scene.boxes) {
      const x1 = x(b.t1);
      const x2 = x(b.t2);
      const y1 = y(b.p1);
      const y2 = y(b.p2);
      if (x1 === null || y1 === null || y2 === null || (b.t2 !== null && x2 === null)) continue;
      boxes.push(b.t2 === null ? { x1: x1 + half, x2: null, y1, y2, b } : { x1: x1 - half, x2: (x2 ?? x1) + half, y1, y2, b });
    }
    const segments: Px['segments'] = [];
    for (const s of this.scene.segments) {
      const yy = y(s.price);
      const x1 = x(s.t1);
      if (yy === null || (s.t1 !== null && x1 === null)) continue;
      segments.push({ x1, y: yy, s });
    }
    const vlines: Px['vlines'] = [];
    for (const v of this.scene.vlines) {
      const xx = x(v.t);
      if (xx !== null) vlines.push({ x: xx, v });
    }
    const tags: Px['tags'] = [];
    for (const t of this.scene.edgeTags) {
      const yy = y(t.price);
      if (yy !== null) tags.push({ y: yy, t });
    }
    const pins: Px['pins'] = [];
    for (const p of this.scene.pins) {
      const xx = x(p.t);
      const yy = y(p.price);
      if (xx !== null && yy !== null) pins.push({ x: xx, y: yy, p });
    }
    const levels: Px['levels'] = [];
    for (const l of this.scene.levels ?? []) {
      const [yy, y1, y2] = [y(l.price), y(l.hi), y(l.lo)];
      if (yy !== null && y1 !== null && y2 !== null) levels.push({ y: yy, y1, y2, l });
    }
    const ticks: Px['ticks'] = [];
    for (const t of this.scene.ticks ?? []) {
      const yy = y(t.price);
      if (yy !== null) ticks.push({ y: yy, t });
    }
    this.px = { boxes, segments, vlines, tags, pins, labels: this.scene.labels, levels, ticks };
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** The story under the pointer: a label drawn for a box (labels sit on top), else the top-most box (the
   * last drawn wins: live lanes over past setups). */
  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    for (let i = this.labelHits.length - 1; i >= 0; i -= 1) {
      const { rect, hoverId } = this.labelHits[i];
      if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
        return { externalId: hoverId, zOrder: 'top' };
      }
    }
    for (let i = this.px.boxes.length - 1; i >= 0; i -= 1) {
      const { x1, x2, y1, y2, b } = this.px.boxes[i];
      if (!b.hoverId || x2 === null) continue;
      const top = Math.min(y1, y2) - HIT_SLACK_PX;
      const bottom = Math.max(y1, y2) + HIT_SLACK_PX;
      if (x >= x1 - HIT_SLACK_PX && x <= x2 + HIT_SLACK_PX && y >= top && y <= bottom) {
        return { externalId: b.hoverId, zOrder: 'top' };
      }
    }
    return null;
  }

  autoscaleInfo(): AutoscaleInfo | null {
    const keep = this.scene.keepInView;
    return keep ? { priceRange: { minValue: keep.min, maxValue: keep.max } } : null;
  }
}
