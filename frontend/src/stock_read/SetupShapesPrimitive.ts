/**
 * Lightweight-charts series primitive for the stock read (ADR 036): the setups' boxes (leg, pole,
 * pullback, flag, base, red phase), the plan's risk and reward zones, level segments, a focus line
 * for a decision the operator asked to see, edge tags for levels above or below the visible
 * prices, and the moment's pin (ENTER NOW, SELL NOW, what Nova did: ADR 037) on its candle. It draws a scene it is given; `chartShapes.ts` decides what the scene holds and
 * `StockReadChartLayer` maps its times onto this pane's bars. A box with a `hoverId` is reported to the
 * chart as hovered (`hitTest`) -- over the box, or over the label it drew for the box -- so the pane can
 * tell that setup's story under the pointer; a level's label or axis tick names the level's card. The scene's
 * shapes are `sceneTypes.ts`; drawing them is `sceneRender.ts` -- where each label goes, and how much a past
 * setup's says (`sceneLabels.ts`), and every word at the right edge in one column (`edgeColumn.ts`): the levels'
 * names, the lines' tags (`words`: the EMAs, VWAP, the plan's ENTRY / STOP / TARGET) and the tags for prices out
 * of view. The Full Day pane's +40% runs are marks: an arrow over the day's high and a label that makes room.
 */
import { MismatchDirection } from 'lightweight-charts';
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
import { publishPaneWords } from '../chart';
import { emptyPx, FillRenderer, LineRenderer, type LabelHit, type Px } from './sceneRender';
import type { LabelRect } from './sceneLabels';
import { EMPTY_SCENE, type Scene } from './sceneTypes';

/** A pointer this close to a box's edge still hovers it. */
const HIT_SLACK_PX = 2;
/** What this primitive's words are published as on the pane (`chart/paneWords.ts`). */
const PANE_WORDS_SOURCE = 'stock-read';

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
    }, rects => this.source.publishWords(rects));
  }

  zOrder(): PrimitivePaneViewZOrder {
    return this.layer === 'fill' ? 'bottom' : 'top';
  }
}

/** A line series' value on logical bar `index`, else the nearest one before it. */
function valueAt(series: ISeriesApi<SeriesType>, index: number): number | null {
  const d = series.dataByIndex(index, MismatchDirection.NearestLeft) as { value?: number } | null;
  return d && typeof d.value === 'number' && Number.isFinite(d.value) ? d.value : null;
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
    if (this.chart) publishPaneWords(this.chart, PANE_WORDS_SOURCE, []);
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
    this.labelHits = [];
  }

  /** The words the last draw put on the pane, for the close countdown to keep clear of. */
  publishWords(rects: readonly LabelRect[]): void {
    if (this.chart) publishPaneWords(this.chart, PANE_WORDS_SOURCE, rects);
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
    // A series' tag sits at its value on the last bar in view, where lightweight-charts puts a series title.
    const range = ts.getVisibleLogicalRange();
    const lastBar = range ? Math.floor(range.to) : null;
    const words: Px['words'] = [];
    for (const w of this.scene.words ?? []) {
      const value = w.price ?? (w.series && lastBar !== null ? valueAt(w.series, lastBar) : null);
      if (value === null) continue;
      const yy = (w.series ?? series).priceToCoordinate(value);
      if (yy !== null) words.push({ y: yy, value, w });
    }
    const reserves: Px['reserves'] = [];
    for (const r of this.scene.reserves ?? []) {
      const yy = y(r.price);
      if (yy !== null) reserves.push({ top: yy - r.height / 2, bottom: yy + r.height / 2 });
    }
    const marks: Px['marks'] = [];
    for (const m of this.scene.marks ?? []) {
      const xx = x(m.t);
      const yy = y(m.price);
      if (xx !== null && yy !== null) marks.push({ x: xx, y: yy, m });
    }
    this.px = { boxes, segments, vlines, tags, pins, labels: this.scene.labels, levels, ticks, words, reserves,
      topInset: this.scene.topInset ?? 0, marks };
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
