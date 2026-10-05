/**
 * The open position's fill arrows on a candle series: an arrow under its bar for a buy, over it for a
 * sell, with the fill price -- drawn the way lightweight-charts' series markers draw them. Display only.
 *
 * Not `createSeriesMarkers`: that plugin asks for a *full* redraw on every data change of its series,
 * so every tick laid out the whole page (the price axis sets a canvas font), on every pane. In 5.1.0
 * its `detached()` also unsubscribes a handler it never stored, so each plugin a re-render replaced
 * kept forcing full redraws until the page reloaded -- the Trader tab drew 5 frames a second by the
 * open. This one asks for a redraw only when its fills change; lightweight-charts refreshes its view
 * on every redraw anyway, a tick's included.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  AutoscaleInfo,
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesMarker,
  SeriesType,
  Time,
} from 'lightweight-charts';
import { publishPaneWords, type PaneWordRect } from './paneWords';

/** What this primitive's arrows and prices are published as on the pane (`paneWords.ts`). */
const PANE_WORDS_SOURCE = 'fill-markers';

/** Lightweight-charts' marker geometry (`series-markers-utils`), so the arrows look as they did. */
const MIN_SHAPE = 12;
const MAX_SHAPE = 30;
const MIN_MARGIN = 3;
const TEXT_MARGIN = 0.1;

function ceiledOdd(x: number): number {
  const c = Math.ceil(x);
  return c % 2 === 0 ? c - 1 : c;
}

function ceiledEven(x: number): number {
  const c = Math.ceil(x);
  return c % 2 !== 0 ? c - 1 : c;
}

function shapeUnit(barSpacing: number, coeff: number): number {
  return ceiledOdd(Math.min(Math.max(barSpacing, MIN_SHAPE), MAX_SHAPE) * coeff);
}

/** An arrow's height on screen for a marker of `size` at this bar spacing. */
export function markerHeight(barSpacing: number, size = 1): number {
  return ceiledEven(shapeUnit(barSpacing, 1)) * Math.max(size, 0);
}

export function markerMargin(barSpacing: number): number {
  return Math.max(shapeUnit(barSpacing, TEXT_MARGIN), MIN_MARGIN);
}

export interface FillMarkerPx {
  x: number;
  /** The arrow's centre. */
  y: number;
  textY: number;
  up: boolean;
  size: number;
  color: string;
  text: string;
}

interface BarRange {
  high: number;
  low: number;
}

/**
 * Pixels for each marker whose bar is in the series: under the bar's low or over its high, the
 * price under (over) the arrow, a second marker on one bar stacked past the first.
 */
export function layoutFillMarkers(
  markers: readonly SeriesMarker<Time>[],
  place: {
    x: (time: Time) => number | null;
    bar: (time: Time) => BarRange | null;
    y: (price: number) => number | null;
    barSpacing: number;
    textHeight: number;
  },
): FillMarkerPx[] {
  const margin = markerMargin(place.barSpacing);
  const offsets = new Map<number, { above: number; below: number }>();
  const out: FillMarkerPx[] = [];
  for (const m of markers) {
    const x = place.x(m.time);
    const bar = place.bar(m.time);
    if (x === null || bar === null) continue;
    const above = m.position === 'aboveBar';
    const y0 = place.y(above ? bar.high : bar.low);
    if (y0 === null) continue;
    const size = markerHeight(place.barSpacing, typeof m.size === 'number' ? m.size : 1);
    const half = size / 2;
    const key = Math.round(x);
    const off = offsets.get(key) ?? { above: margin, below: margin };
    offsets.set(key, off);
    const text = m.text ?? '';
    const textStep = text ? place.textHeight * (1 + 2 * TEXT_MARGIN) : 0;
    const textGap = place.textHeight * (0.5 + TEXT_MARGIN);
    let y: number;
    let textY: number;
    if (above) {
      y = y0 - half - off.above;
      textY = y - half - textGap;
      off.above += textStep + size + margin;
    } else {
      y = y0 + half + off.below;
      textY = y + half + margin + textGap;
      off.below += textStep + size + margin;
    }
    out.push({ x, y, textY, up: !above, size, color: m.color ?? '', text });
  }
  return out;
}

class FillMarkersRenderer implements IPrimitivePaneRenderer {
  private readonly items: readonly FillMarkerPx[];
  private readonly font: string;
  private readonly textHeight: number;
  private readonly onWords: (rects: PaneWordRect[]) => void;

  constructor(items: readonly FillMarkerPx[], font: string, textHeight: number,
    onWords: (rects: PaneWordRect[]) => void) {
    this.items = items;
    this.font = font;
    this.textHeight = textHeight;
    this.onWords = onWords;
  }

  draw(target: CanvasRenderingTarget2D): void {
    if (this.items.length === 0) {
      this.onWords([]);
      return;
    }
    target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hpr, verticalPixelRatio: vpr }) => {
      for (const m of this.items) {
        ctx.fillStyle = m.color;
        drawArrow(ctx, m.up, Math.round(m.x * hpr), m.y * vpr, m.size, hpr);
      }
    });
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      ctx.font = this.font;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      // The arrows and their prices are words on the pane too: the close countdown keeps clear of them.
      const words: PaneWordRect[] = [];
      for (const m of this.items) {
        words.push({ left: m.x - m.size / 2, top: m.y - m.size / 2, right: m.x + m.size / 2, bottom: m.y + m.size / 2 });
        if (!m.text) continue;
        ctx.fillStyle = m.color;
        ctx.fillText(m.text, m.x, m.textY);
        const half = ctx.measureText(m.text).width / 2;
        words.push({ left: m.x - half, top: m.textY - this.textHeight / 2, right: m.x + half,
          bottom: m.textY + this.textHeight / 2 });
      }
      this.onWords(words);
    });
  }
}

/** Lightweight-charts' `drawArrow`: a head and a stem, pointing up (a buy) or down (a sell). */
function drawArrow(ctx: CanvasRenderingContext2D, up: boolean, x: number, y: number, size: number, ratio: number): void {
  const head = ((shapeUnit(size, 1) - 1) / 2) * ratio;
  const stem = ((ceiledOdd(size / 2) - 1) / 2) * ratio;
  const dir = up ? -1 : 1;
  ctx.beginPath();
  ctx.moveTo(x - head, y);
  ctx.lineTo(x, y + dir * head);
  ctx.lineTo(x + head, y);
  ctx.lineTo(x + stem, y);
  ctx.lineTo(x + stem, y - dir * head);
  ctx.lineTo(x - stem, y - dir * head);
  ctx.lineTo(x - stem, y);
  ctx.fill();
}

class FillMarkersView implements IPrimitivePaneView {
  private readonly source: FillMarkersPrimitive;

  constructor(source: FillMarkersPrimitive) {
    this.source = source;
  }

  renderer(): IPrimitivePaneRenderer {
    return new FillMarkersRenderer(this.source.px, this.source.font, this.source.fontSize,
      rects => this.source.publishWords(rects));
  }
}

export class FillMarkersPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private markers: readonly SeriesMarker<Time>[] = [];
  private key = '';
  private readonly views = [new FillMarkersView(this)];
  px: FillMarkerPx[] = [];
  font = '';
  fontSize = 12;

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
    if (this.markers.length > 0) this.requestUpdate();
  }

  detached(): void {
    if (this.chart) publishPaneWords(this.chart, PANE_WORDS_SOURCE, []);
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
    this.px = [];
  }

  publishWords(rects: readonly PaneWordRect[]): void {
    if (this.chart) publishPaneWords(this.chart, PANE_WORDS_SOURCE, rects);
  }

  /** New fills redraw the pane; the same fills again do nothing. */
  setMarkers(markers: readonly SeriesMarker<Time>[]): void {
    const key = markers.map(m => `${m.id}:${String(m.time)}:${m.position}:${m.text}:${m.color}`).join('|');
    if (key === this.key) return;
    this.key = key;
    this.markers = markers;
    this.requestUpdate?.();
  }

  updateAllViews(): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series || this.markers.length === 0) {
      this.px = [];
      return;
    }
    const ts = chart.timeScale();
    const layout = chart.options().layout;
    this.font = `${layout.fontSize}px ${layout.fontFamily}`;
    this.fontSize = layout.fontSize;
    this.px = layoutFillMarkers(this.markers, {
      x: t => ts.timeToCoordinate(t),
      bar: t => {
        const index = ts.timeToIndex(t, false);
        const d = index === null ? null : (series.dataByIndex(index) as Partial<BarRange> | null);
        return d && typeof d.high === 'number' && typeof d.low === 'number' ? { high: d.high, low: d.low } : null;
      },
      y: p => series.priceToCoordinate(p),
      barSpacing: ts.options().barSpacing,
      textHeight: layout.fontSize,
    });
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** Room over and under the candles for the arrows and their prices, as the markers plugin kept. */
  autoscaleInfo(): AutoscaleInfo | null {
    if (this.markers.length === 0 || !this.chart) return null;
    const layout = this.chart.options().layout;
    const spacing = this.chart.timeScale().options().barSpacing;
    const room = (pos: SeriesMarker<Time>['position']) => {
      const ms = this.markers.filter(m => m.position === pos);
      if (ms.length === 0) return 0;
      const size = Math.max(...ms.map(m => markerHeight(spacing, typeof m.size === 'number' ? m.size : 1)));
      return size + 2 * markerMargin(spacing) + layout.fontSize * (1 + 2 * TEXT_MARGIN);
    };
    return { priceRange: null, margins: { above: room('aboveBar'), below: room('belowBar') } };
  }
}
