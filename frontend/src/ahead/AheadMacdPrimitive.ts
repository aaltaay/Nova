/**
 * Ahead's MACD fan (ADR 061) on the MACD pane under the 1-minute chart: the hatched zone, two bands (10-90 and 25-75)
 * of the MACD line worked out from the forecaster's paths, starting at the last real MACD point, and the caption
 * that says so. The MACD is never forecast directly; `macdFromPaths.ts` runs Nova's own MACD over the real closes and
 * each path. The pane's logical range follows the price chart's, so step `k` sits at the same bar position there.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
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
import { AHEAD_DRAW, band, hatch, words, type Pt } from './aheadCanvas';
import { stepper } from './AheadPrimitive';
import type { SceneBand } from './aheadSceneTypes';

export interface MacdFanInput {
  /** The anchor candle (chart seconds), the zone's steps and the fan per step; null bands: zone only. */
  anchorT: number;
  horizon: number;
  bands: SceneBand[] | null;
  caption: string;
}

export interface MacdPx {
  left: number;
  right: number;
  from: Pt;
  xs: number[];
  q: { q10: number[]; q25: number[]; q75: number[]; q90: number[] };
  caption: string;
}

class MacdRenderer implements IPrimitivePaneRenderer {
  private readonly px: MacdPx | null;
  private readonly layer: 'under' | 'over';

  constructor(px: MacdPx | null, layer: 'under' | 'over') {
    this.px = px;
    this.layer = layer;
  }

  draw(target: CanvasRenderingTarget2D): void {
    const g = this.px;
    if (!g) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const right = Math.min(g.right, mediaSize.width);
      if (right <= g.left) return;
      if (this.layer === 'under') {
        hatch(ctx, { left: g.left, top: 0, right, bottom: mediaSize.height }, AHEAD_DRAW.zone, AHEAD_DRAW.stripe);
        return;
      }
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, right, mediaSize.height);
      ctx.clip();
      band(ctx, g.from, g.xs, g.q.q90, g.q.q10, AHEAD_DRAW.ai, AHEAD_DRAW.macdOuter);
      band(ctx, g.from, g.xs, g.q.q75, g.q.q25, AHEAD_DRAW.ai, AHEAD_DRAW.macdInner);
      ctx.restore();
      words(ctx, g.left + 8, 14, g.caption, AHEAD_DRAW.aiText, 'left', '600 11px ui-sans-serif, system-ui, sans-serif');
    });
  }
}

class MacdView implements IPrimitivePaneView {
  private readonly src: AheadMacdPrimitive;
  private readonly layer: 'under' | 'over';

  constructor(src: AheadMacdPrimitive, layer: 'under' | 'over') {
    this.src = src;
    this.layer = layer;
  }

  renderer(): IPrimitivePaneRenderer {
    return new MacdRenderer(this.src.px, this.layer);
  }

  zOrder(): PrimitivePaneViewZOrder {
    return this.layer === 'under' ? 'bottom' : 'top';
  }
}

export class AheadMacdPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private input: MacdFanInput | null = null;
  private readonly views = [new MacdView(this, 'under'), new MacdView(this, 'over')];
  px: MacdPx | null = null;

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
    this.px = null;
  }

  setFan(input: MacdFanInput | null): void {
    this.input = input;
    this.requestUpdate?.();
  }

  updateAllViews(): void {
    this.px = this.layout();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  hitTest(): null {
    return null;
  }

  private layout(): MacdPx | null {
    const chart = this.chart;
    const series = this.series;
    const f = this.input;
    if (!chart || !series || !f?.bands?.length) return null;
    const step = stepper(chart, f.anchorT);
    if (!step) return null;
    const x0 = step.x(0);
    const xEnd = step.x(f.horizon);
    const row = series.dataByIndex(step.idx) as { value?: number } | null;
    const y0 = typeof row?.value === 'number' ? series.priceToCoordinate(row.value) : null;
    if (x0 === null || xEnd === null || y0 === null) return null;
    const xs: number[] = [];
    const q = { q10: [] as number[], q25: [] as number[], q75: [] as number[], q90: [] as number[] };
    for (const b of f.bands) {
      const x = step.x(b.k);
      const ys = [b.q10, b.q25, b.q75, b.q90].map(v => series.priceToCoordinate(v));
      if (x === null || ys.some(v => v === null)) continue;
      xs.push(x);
      q.q10.push(ys[0] as number);
      q.q25.push(ys[1] as number);
      q.q75.push(ys[2] as number);
      q.q90.push(ys[3] as number);
    }
    return { left: x0 + step.half, right: xEnd + step.half, from: { x: x0, y: y0 }, xs, q, caption: f.caption };
  }
}
