/**
 * Ahead on the 1-minute pane (ADR 061): the hatched zone right of the newest completed candle, the forecaster's fan and
 * drawn paths, Nova's own lines carried on to where they meet, the walls' or the setup's stubs inside the zone, the odds
 * chips at its right edge, "now HH:MM" left of it and a minute label every 5 minutes along its bottom.
 *
 * It draws the scene `aheadScene.ts` decided and does pixel math only: step `k` sits at
 * `logicalToCoordinate(indexOf(anchorT) + k)`. Nothing is added to any series (no bars, no whitespace, no
 * `rightOffset`), so a forecast can never pass for a candle; the zone stops short of the stock read's word column at
 * the right edge, and its words are published to the pane (`publishPaneWords`) for the close countdown to keep clear.
 */
import type {
  AutoscaleInfo,
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Logical,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import { paneWordsExcept, publishPaneWords, subscribePaneWords } from '../chart';
import { AHEAD_DRAW, band, chip, dashed, hatch, overlaps, polyline, ring, words, type Pt, type Rect } from './aheadCanvas';
import type { AheadScene } from './aheadSceneTypes';

/** What this primitive's words are published as on the pane (`chart/paneWords.ts`). */
export const AHEAD_WORDS_SOURCE = 'ahead';
/** The stock read's word column ends this close to the pane's right edge (`stock_read/edgeColumn.ts`). */
const COLUMN_EDGE_SLACK_PX = 16;
/** The zone never gives the word column more than this share of the pane. */
const COLUMN_MAX_SHARE = 0.45;
const MEET_RING_PX = 6;
const CHIP_GAP_PX = 2;
const CHIP_STEP_PX = 20;

/** Where the zone's heading goes, in the pane's pixels; null when no zone is drawn. */
export type ZoneLayout = { left: number; right: number; top: number } | null;

/** Room the stock read's word column holds at the pane's right edge (px), from the words it published. Ahead's own
 * words are left out: its chips sit at the zone's edge, so counting them would move the clip they were placed by and
 * repaint forever. */
export function edgeInset(chart: IChartApi | null, width: number): number {
  let left = width;
  for (const r of paneWordsExcept(chart, AHEAD_WORDS_SOURCE)) {
    if (r.right >= width - COLUMN_EDGE_SLACK_PX && r.left < left) left = r.left;
  }
  return Math.min(width - left, width * COLUMN_MAX_SHARE);
}

/** The anchor's logical index and a step's x on this chart (null off the time scale). */
export function stepper(chart: IChartApi, anchorT: number | null): { idx: number; x: (k: number) => number | null;
  half: number } | null {
  if (anchorT === null) return null;
  const ts = chart.timeScale();
  const idx = ts.timeToIndex(anchorT as Time, false);
  if (idx === null) return null;
  return {
    idx,
    x: (k: number) => ts.logicalToCoordinate((idx + k) as Logical),
    half: (ts.options().barSpacing || 6) / 2,
  };
}

interface Px {
  anchor: Pt;
  /** Zone left (the anchor candle's right edge) and its unclipped right. */
  left: number;
  right: number;
  xs: Map<number, number>;
  y: (p: number) => number | null;
  scene: AheadScene;
}

class AheadRenderer implements IPrimitivePaneRenderer {
  private readonly src: AheadPrimitive;
  private readonly layer: 'under' | 'over';

  constructor(src: AheadPrimitive, layer: 'under' | 'over') {
    this.src = src;
    this.layer = layer;
  }

  draw(target: CanvasRenderingTarget2D): void {
    const px = this.src.px;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width;
      const H = mediaSize.height;
      if (!px) {
        if (this.layer === 'over') this.src.drawn(null, [], W);
        return;
      }
      const right = Math.min(px.right, W - edgeInset(this.src.chartApi, W));
      if (right <= px.left) {
        if (this.layer === 'over') this.src.drawn(null, [], W);
        return;
      }
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, right, H);
      ctx.clip();
      if (this.layer === 'under') {
        this.under(ctx, px, right, H);
        ctx.restore();
        return;
      }
      const rects = this.over(ctx, px, right, W, H);
      ctx.restore();
      // "now HH:MM" sits left of the zone, outside its clip.
      const now = px.scene.zone ? chip(ctx, px.left - 4, 14, px.scene.zone.nowText, AHEAD_DRAW.text, AHEAD_DRAW.nowBg,
        'end', { width: W, height: H }) : null;
      this.src.drawn({ left: px.left, right, top: 0 }, now ? [...rects, now] : rects, W);
    });
  }

  private under(ctx: CanvasRenderingContext2D, px: Px, right: number, H: number): void {
    const s = px.scene;
    hatch(ctx, { left: px.left, top: 0, right, bottom: H }, AHEAD_DRAW.zone, AHEAD_DRAW.stripe);
    dashed(ctx, { x: px.left, y: 0 }, { x: px.left, y: H }, AHEAD_DRAW.muted, [3, 3], 1);
    const steps = (s.fan ?? []).filter(b => px.xs.has(b.k));
    if (steps.length) {
      const xs = steps.map(b => px.xs.get(b.k) as number);
      const ys = (pick: (b: (typeof steps)[number]) => number) => steps.map(b => px.y(pick(b)) ?? px.anchor.y);
      const dim = this.src.fanDim ? AHEAD_DRAW.fanDim : 1;
      band(ctx, px.anchor, xs, ys(b => b.q90), ys(b => b.q10), AHEAD_DRAW.ai, AHEAD_DRAW.fanOuter * dim);
      band(ctx, px.anchor, xs, ys(b => b.q75), ys(b => b.q25), AHEAD_DRAW.ai, AHEAD_DRAW.fanInner * dim);
    }
    for (const path of s.paths) {
      const pts: Pt[] = [px.anchor];
      path.points.forEach((p, i) => {
        const x = px.xs.get(i + 1);
        const y = px.y(p);
        if (x !== undefined && y !== null) pts.push({ x, y });
      });
      polyline(ctx, pts, path.color, path.alpha);
    }
  }

  /** The lines, the stubs and every chip; returns the rectangles its words hold. */
  private over(ctx: CanvasRenderingContext2D, px: Px, right: number, W: number, H: number): Rect[] {
    const s = px.scene;
    const bounds = { width: Math.min(W, right + 1), height: H };
    const rects: Rect[] = [];
    const put = (r: Rect | null) => {
      if (r) rects.push(r);
    };
    const at = (k: number) => this.src.stepX(k);
    for (const line of s.lines) {
      const xb = at(line.toSteps);
      const ya = px.y(line.fromP);
      const yb = px.y(line.fromP + line.slope * line.toSteps);
      if (xb === null || ya === null || yb === null) continue;
      dashed(ctx, { x: px.anchor.x, y: ya }, { x: xb, y: yb }, line.color, [2, 5], 2, true);
    }
    if (s.meet) {
      const xm = at(Math.min(s.meet.steps, s.horizon));
      const ym = px.y(s.meet.p);
      if (xm !== null && ym !== null) {
        if (s.meet.inZone) ring(ctx, { x: xm, y: ym }, MEET_RING_PX, AHEAD_DRAW.ring);
        put(chip(ctx, xm - 4, ym - 14, s.meet.text, AHEAD_DRAW.text, AHEAD_DRAW.chipBg, 'end', bounds));
      }
    }
    for (const h of s.hLines) {
      const y = px.y(h.p);
      if (y === null) continue;
      dashed(ctx, { x: px.left, y }, { x: right, y }, h.color, h.dash, 1.6);
      if (h.chip) put(chip(ctx, right - 6, y - 11, h.chip, h.color, AHEAD_DRAW.chipBg, 'end', bounds));
    }
    // The odds chips at the zone's right edge, nudged apart so none covers another.
    const placed: Rect[] = [...rects];
    const chips = s.chips.map(c => ({ c, y: px.y(c.p) })).filter(c => c.y !== null)
      .sort((a, b) => (a.y as number) - (b.y as number));
    for (const { c, y } of chips) {
      let cy = y as number;
      for (let tries = 0; tries < 8; tries += 1) {
        const probe = { left: right - 200, right: right - 6, top: cy - 9, bottom: cy + 9 };
        if (!placed.some(r => overlaps(r, probe, CHIP_GAP_PX))) break;
        cy += CHIP_STEP_PX;
      }
      const r = chip(ctx, right - 6, cy, c.text, c.color, AHEAD_DRAW.chipBg, 'end', bounds);
      if (r) {
        placed.push(r);
        rects.push(r);
      }
    }
    for (const t of s.ticks) {
      const x = px.xs.get(t.k);
      if (x !== undefined && x < right - 12) words(ctx, x, H - 6, t.text, AHEAD_DRAW.muted);
    }
    return rects;
  }
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

export class AheadPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private scene: AheadScene | null = null;
  private readonly views = [new AheadView(this, 'under'), new AheadView(this, 'over')];
  private layout: ZoneLayout = null;
  private onLayout: ((z: ZoneLayout) => void) | null = null;
  private extra: Rect[] = [];
  private unsubscribeWords: (() => void) | null = null;
  private insetUsed = 0;
  private widthUsed = 0;
  px: Px | null = null;
  fanDim = false;

  get chartApi(): IChartApi | null {
    return this.chart;
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
    // The word column at the right edge can change after this paint: draw the zone's clip again when it did.
    this.unsubscribeWords = subscribePaneWords(param.chart, () => {
      if (this.px && edgeInset(this.chart, this.widthUsed) !== this.insetUsed) this.requestUpdate?.();
    });
    this.requestUpdate();
  }

  detached(): void {
    this.unsubscribeWords?.();
    this.unsubscribeWords = null;
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
  drawn(zone: ZoneLayout, rects: Rect[], width: number): void {
    this.widthUsed = width;
    this.insetUsed = edgeInset(this.chart, width);
    if (this.chart) publishPaneWords(this.chart, AHEAD_WORDS_SOURCE, zone ? [...rects, ...this.extra] : []);
    const wasDrawn = this.layout !== null;
    this.setLayout(zone);
    // The price scale keeps the forecast in view only while the zone is on screen: once more when that flips.
    if (wasDrawn !== (zone !== null)) this.requestUpdate?.();
  }

  updateAllViews(): void {
    this.px = this.layoutPx();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
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

  private setLayout(z: ZoneLayout): void {
    const was = this.layout;
    if (was === null && z === null) return;
    if (was && z && Math.abs(was.left - z.left) < 1 && Math.abs(was.right - z.right) < 1) return;
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
      right: xEnd + step.half,
      xs,
      y: (p: number) => series.priceToCoordinate(p),
      scene: s,
    };
  }
}
