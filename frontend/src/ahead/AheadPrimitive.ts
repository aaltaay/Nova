/**
 * Ahead on the 1-minute pane (ADR 065): the hatched zone right of the newest completed candle, the forecaster's fan and
 * drawn paths, Nova's own lines carried on to where they meet, the walls' or the setup's stubs inside the zone, the odds
 * chips at its right edge and a minute label every 5 minutes on the time axis under it ("now HH:MM" left of it and the
 * heading are DOM, `AheadHeading.tsx`, so no line drawn on the pane ever crosses them). The pixels are
 * `AheadZoneRenderer.ts`'s; the forecast's prices stay above the volume band (`setVolumeSeries`).
 *
 * It draws the scene `aheadScene.ts` decided and does pixel math only: step `k` sits at
 * `logicalToCoordinate(indexOf(anchorT) + k)`, a fractional step between its two whole neighbours. Nothing is added
 * to any series (no bars, no whitespace, no `rightOffset`), so a forecast can never pass for a candle. The zone always
 * runs its full 15 steps (the MACD pane's runs the same), the framing (`useAheadRoom.ts`) leaves the stock read's word
 * column room right of it, no chip ever leaves the zone (a narrow zone gets the odds-only chip, or none), and its
 * words are published to the pane (`publishPaneWords`) for the close countdown to keep clear.
 */
import type {
  AutoscaleInfo,
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitiveAxisView,
  Logical,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';
import { paneWordsExcept, publishPaneWords } from '../chart';
import type { Rect } from './aheadCanvas';
import { AHEAD_COLORS } from './aheadConstants';
import type { AheadScene } from './aheadSceneTypes';
import { AheadRenderer, type Px, type ZoneSource } from './AheadZoneRenderer';

/** What this primitive's words are published as on the pane (`chart/paneWords.ts`). */
export const AHEAD_WORDS_SOURCE = 'ahead';
/** The stock read's word column ends this close to the pane's right edge (`stock_read/edgeColumn.ts`). */
const COLUMN_EDGE_SLACK_PX = 16;
/** The zone never gives the word column more than this share of the pane. */
const COLUMN_MAX_SHARE = 0.45;
/** A ghost volume bar's width as a share of a step; the zone ends just past the last one (`stepper().tail`). */
export const GHOST_BAR_SHARE = 0.62;

/** Where the zone's heading goes, in the pane's pixels; null when no zone is drawn. */
export type ZoneLayout = {
  left: number;
  right: number;
  top: number;
  /** Where the heading must end: left of the pane's other words over the zone's top (the stock read's labels), so
   * its backdrop never hides them; absent, the zone's right. */
  capRight?: number;
} | null;
/** The band at the zone's top the heading takes (title, tags and a sentence), px. */
export const HEADING_BAND_PX = 64;

/** Room the stock read's word column holds at the pane's right edge (px), from the words it published -- the framing
 * leaves it right of the zone. Ahead's own words are left out: its chips sit at the zone's edge. */
export function edgeInset(chart: IChartApi | null, width: number): number {
  let left = width;
  for (const r of paneWordsExcept(chart, AHEAD_WORDS_SOURCE)) {
    if (r.right >= width - COLUMN_EDGE_SLACK_PX && r.left < left) left = r.left;
  }
  return Math.min(width - left, width * COLUMN_MAX_SHARE);
}

/** The anchor's logical index and a step's x on this chart (null off the time scale). A fractional step (the lines'
 * meet) is placed between its two whole neighbours: lightweight-charts places whole indexes only (a fractional one
 * comes back as 0, the pane's left edge). */
export function stepper(chart: IChartApi, anchorT: number | null): { idx: number; x: (k: number) => number | null;
  half: number; tail: number } | null {
  if (anchorT === null) return null;
  const ts = chart.timeScale();
  const idx = ts.timeToIndex(anchorT as Time, false);
  if (idx === null) return null;
  const whole = (i: number) => ts.logicalToCoordinate((idx + i) as Logical);
  const half = (ts.options().barSpacing || 6) / 2;
  return {
    idx,
    x: (k: number) => {
      const lo = Math.floor(k);
      const xa = whole(lo);
      if (k === lo || xa === null) return xa;
      const xb = whole(lo + 1);
      return xb === null ? null : xa + (xb - xa) * (k - lo);
    },
    half,
    tail: half * GHOST_BAR_SHARE + 1,
  };
}

class AheadView implements IPrimitivePaneView {
  private readonly src: AheadPrimitive;
  private readonly layer: 'under' | 'over';

  constructor(src: AheadPrimitive, layer: 'under' | 'over') {
    this.src = src;
    this.layer = layer;
  }

  renderer(): IPrimitivePaneRenderer {
    return new AheadRenderer(this.src, this.layer);
  }

  zOrder(): PrimitivePaneViewZOrder {
    return this.layer === 'under' ? 'bottom' : 'top';
  }
}

/** The top of a volume overlay's band on its pane (px): its scale's top margin; null without one. */
export function volumeBandTop(chart: IChartApi, volume: ISeriesApi<SeriesType> | null): number | null {
  if (!volume) return null;
  const top = volume.priceScale().options().scaleMargins?.top;
  return typeof top === 'number' && top > 0 ? chart.paneSize().height * top : null;
}

export class AheadPrimitive implements ISeriesPrimitive<Time>, ZoneSource {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private volume: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private scene: AheadScene | null = null;
  private readonly views = [new AheadView(this, 'under'), new AheadView(this, 'over')];
  private layout: ZoneLayout = null;
  private onLayout: ((z: ZoneLayout) => void) | null = null;
  private extra: Rect[] = [];
  px: Px | null = null;
  fanDim = false;

  get chartApi(): IChartApi | null {
    return this.chart;
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
    this.requestUpdate();
  }

  detached(): void {
    if (this.chart) publishPaneWords(this.chart, AHEAD_WORDS_SOURCE, []);
    this.setLayout(null);
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
    this.px = null;
  }

  /** The scene to draw; `fanDim` on a strategy scope, where the coloured paths read first. */
  setScene(scene: AheadScene | null, fanDim = false): void {
    this.scene = scene;
    this.fanDim = fanDim;
    this.requestUpdate?.();
  }

  /** The pane's volume overlay: the forecast's prices are drawn above its band, never over its bars. */
  setVolumeSeries(volume: ISeriesApi<SeriesType> | null): void {
    this.volume = volume;
    this.requestUpdate?.();
  }

  /** Called with the zone's place whenever it moves by a pixel or more (the DOM heading follows it). */
  setLayoutListener(fn: ((z: ZoneLayout) => void) | null): void {
    this.onLayout = fn;
    fn?.(this.layout);
  }

  /** Words drawn over the zone outside the canvas (the DOM heading), kept clear by the close countdown too. */
  setExtraWords(rects: Rect[]): void {
    this.extra = rects;
  }

  /** Step `k`'s x from the anchor (fractional steps too); null without an anchor on this pane. */
  stepX(k: number): number | null {
    if (!this.chart || !this.px) return null;
    return stepper(this.chart, this.px.scene.anchorT)?.x(k) ?? null;
  }

  /** After a draw: where the zone went and the words it holds. */
  drawn(zone: ZoneLayout, rects: Rect[]): void {
    if (this.chart) publishPaneWords(this.chart, AHEAD_WORDS_SOURCE, zone ? [...rects, ...this.extra] : []);
    const wasDrawn = this.layout !== null;
    this.setLayout(zone ? { ...zone, capRight: this.capRight(zone) } : null);
    // The price scale keeps the forecast in view only while the zone is on screen: once more when that flips.
    if (wasDrawn !== (zone !== null)) this.requestUpdate?.();
  }

  updateAllViews(): void {
    this.px = this.layoutPx();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** The zone's minute labels on the time axis, under the zone, where nothing else of Ahead draws. */
  timeAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    const px = this.px;
    if (!px) return [];
    const out: ISeriesPrimitiveAxisView[] = [];
    for (const t of px.scene.ticks) {
      const x = px.xs.get(t.k);
      if (x === undefined) continue;
      out.push({
        coordinate: () => x,
        text: () => t.text,
        textColor: () => AHEAD_COLORS.axisTick,
        backColor: () => AHEAD_COLORS.axisTickBg,
        tickVisible: () => false,
      });
    }
    return out;
  }

  autoscaleInfo(_start: Logical, end: Logical): AutoscaleInfo | null {
    const s = this.scene;
    const keep = s?.on ? s.keepInView : null;
    // Only what is drawn: no zone on screen (clipped to nothing, off the time scale) stretches no price scale.
    if (!keep || !this.chart || this.layout === null) return null;
    const step = stepper(this.chart, s?.anchorT ?? null);
    if (!step || end < step.idx) return null;
    return { priceRange: { minValue: keep.lo, maxValue: keep.hi } };
  }

  hitTest(): null {
    return null;
  }

  /** The left edge of the leftmost other word starting inside the zone, over its top band (the zone's right with none). */
  private capRight(z: NonNullable<ZoneLayout>): number {
    let cap = z.right;
    for (const r of paneWordsExcept(this.chart, AHEAD_WORDS_SOURCE)) {
      if (r.top < HEADING_BAND_PX && r.bottom > z.top && r.left > z.left && r.left < cap) cap = r.left;
    }
    return cap;
  }

  private setLayout(z: ZoneLayout): void {
    const was = this.layout;
    if (was === null && z === null) return;
    const same = (a?: number, b?: number) => Math.abs((a ?? 0) - (b ?? 0)) < 1;
    if (was && z && same(was.left, z.left) && same(was.right, z.right) && same(was.capRight, z.capRight)) return;
    this.layout = z;
    this.onLayout?.(z);
  }

  private layoutPx(): Px | null {
    const chart = this.chart;
    const series = this.series;
    const s = this.scene;
    if (!chart || !series || !s || !s.on || !s.zone) return null;
    const step = stepper(chart, s.anchorT);
    if (!step) return null;
    const x0 = step.x(0);
    const row = series.dataByIndex(step.idx) as { close?: number; value?: number } | null;
    const close = row?.close ?? row?.value;
    const y0 = typeof close === 'number' ? series.priceToCoordinate(close) : null;
    const xEnd = step.x(s.horizon);
    if (x0 === null || y0 === null || xEnd === null) return null;
    const xs = new Map<number, number>();
    for (let k = 1; k <= s.horizon; k += 1) {
      const x = step.x(k);
      if (x !== null) xs.set(k, x);
    }
    return {
      anchor: { x: x0, y: y0 },
      left: x0 + step.half,
      right: xEnd + step.tail,
      xs,
      y: (p: number) => series.priceToCoordinate(p),
      priceBottom: volumeBandTop(chart, this.volume),
      scene: s,
    };
  }
}
