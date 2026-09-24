/**
 * Lightweight-charts series primitive for the stock read (ADR 036): the setups' boxes (leg, pole,
 * pullback, flag, base, red phase), the plan's risk and reward zones, level segments, a focus line
 * for a decision the operator asked to see, and edge tags for levels above or below the visible
 * prices. It draws a scene it is given; `chartShapes.ts` decides what the scene holds and
 * `StockReadChartLayer` maps its times onto this pane's bars.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  AutoscaleInfo,
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

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

export interface Scene {
  boxes: SceneBox[];
  segments: SceneSegment[];
  vlines: SceneVLine[];
  edgeTags: SceneEdgeTag[];
  /** Prices the pane's autoscale must keep in view (the plan's stop and target). */
  keepInView: { min: number; max: number } | null;
}

export const EMPTY_SCENE: Scene = { boxes: [], segments: [], vlines: [], edgeTags: [], keepInView: null };

const FONT = '600 10px ui-sans-serif, system-ui, sans-serif';
const TAG_TOP = 26;
const TAG_H = 15;

interface Px {
  boxes: { x1: number; x2: number | null; y1: number; y2: number; b: SceneBox }[];
  segments: { x1: number | null; y: number; s: SceneSegment }[];
  vlines: { x: number; v: SceneVLine }[];
  tags: { y: number; t: SceneEdgeTag }[];
}

function label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, color: string, align: 'left' | 'right'): void {
  ctx.font = FONT;
  const w = ctx.measureText(text).width + 8;
  const left = align === 'left' ? x : x - w;
  ctx.fillStyle = 'rgba(12, 12, 14, 0.78)';
  ctx.fillRect(left, y - 7, w, 14);
  ctx.fillStyle = color;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillText(text, left + 4, y + 0.5);
}

class FillRenderer implements IPrimitivePaneRenderer {
  private readonly px: Px;

  constructor(px: Px) {
    this.px = px;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
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

  constructor(px: Px) {
    this.px = px;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.lineWidth = 1;
      for (const { x1, x2, y1, y2, b } of this.px.boxes) {
        const right = x2 ?? mediaSize.width;
        const top = Math.min(y1, y2);
        if (b.stroke) {
          ctx.strokeStyle = b.stroke;
          ctx.setLineDash(b.dashed ? [4, 3] : []);
          ctx.strokeRect(Math.round(x1) + 0.5, Math.round(top) + 0.5, Math.max(1, right - x1), Math.max(1, Math.abs(y2 - y1)));
        }
        if (b.label) {
          const y = b.labelBelow ? Math.max(y1, y2) + 9 : top - 9;
          label(ctx, b.label, x1, y, b.labelColor, 'left');
        }
      }
      for (const { x1, y, s } of this.px.segments) {
        const left = x1 ?? 0;
        ctx.strokeStyle = s.color;
        ctx.setLineDash(s.dashed ? [3, 3] : []);
        ctx.beginPath();
        ctx.moveTo(left, Math.round(y) + 0.5);
        ctx.lineTo(mediaSize.width, Math.round(y) + 0.5);
        ctx.stroke();
        if (s.label) label(ctx, s.label, left + 4, y - 8, s.color, 'left');
      }
      ctx.setLineDash([2, 3]);
      for (const { x, v } of this.px.vlines) {
        ctx.strokeStyle = v.color;
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, 0);
        ctx.lineTo(Math.round(x) + 0.5, mediaSize.height);
        ctx.stroke();
        if (v.label) {
          const right = x > mediaSize.width * 0.6;
          label(ctx, v.label, right ? x - 4 : x + 4, mediaSize.height - 12, v.color, right ? 'right' : 'left');
        }
      }
      ctx.setLineDash([]);
      let up = 0;
      let down = 0;
      for (const { y, t } of this.px.tags) {
        if (y < 0) {
          label(ctx, `↑ ${t.label}`, mediaSize.width - 6, TAG_TOP + up * TAG_H, t.color, 'right');
          up += 1;
        } else if (y > mediaSize.height) {
          label(ctx, `↓ ${t.label}`, mediaSize.width - 6, mediaSize.height - 10 - down * TAG_H, t.color, 'right');
          down += 1;
        }
      }
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
    return this.layer === 'fill' ? new FillRenderer(this.source.px) : new LineRenderer(this.source.px);
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
  px: Px = { boxes: [], segments: [], vlines: [], tags: [] };

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
  }

  setScene(scene: Scene): void {
    this.scene = scene;
    this.requestUpdate?.();
  }

  updateAllViews(): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) {
      this.px = { boxes: [], segments: [], vlines: [], tags: [] };
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
    this.px = { boxes, segments, vlines, tags };
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  autoscaleInfo(): AutoscaleInfo | null {
    const keep = this.scene.keepInView;
    return keep ? { priceRange: { minValue: keep.min, maxValue: keep.max } } : null;
  }
}
