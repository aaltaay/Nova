/**
 * Ahead's ghost volume (ADR 065) on the 1-minute pane's volume histogram: per forecast minute an outline from the
 * volume base to the forecaster's middle guess (q50) and a whisker from q10 to q90, with "AI volume" just over the
 * ghosts under it, on a chip so the price paths that run down into the volume band never cross its words. The ghost
 * runs the zone's full 15 steps, as the price and MACD panes' zones do.
 *
 * Volume is an overlay histogram inside the price pane, so the ghost must never rescale it: there is no
 * `autoscaleInfo` here, and a whisker or outline taller than the volume band is clipped at the band's top with a small
 * caret saying so. It never calls `setData` or `update` on the series.
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
import { AHEAD_DRAW, chip, CHIP_H, chipWidth } from './aheadCanvas';
import { GHOST_BAR_SHARE, stepper } from './AheadPrimitive';
import type { AheadScene } from './aheadSceneTypes';

const CARET_PX = 3;
const MIN_BAR_PX = 3;
/** "AI volume" sits this far over the ghosts under it, this far in from the zone's left edge. */
const LABEL_GAP_PX = 3;
const LABEL_INSET_PX = 6;

export interface GhostBarPx {
  x: number;
  yBase: number;
  y10: number;
  y50: number;
  y90: number;
}

export interface GhostPx {
  left: number;
  right: number;
  /** The top of the volume band (the volume scale's top margin). */
  bandTop: number;
  barW: number;
  bars: GhostBarPx[];
  label: string;
}

/** The label chip's centre: right over the ghosts under its `width` (their whisker tops, cut at the band's top). */
export function labelY(g: GhostPx, width: number): number {
  const left = g.left + LABEL_INSET_PX;
  const under = g.bars.filter(b => b.x + g.barW / 2 >= left && b.x - g.barW / 2 <= left + width);
  const top = under.length ? Math.max(g.bandTop, Math.min(...under.map(b => b.y90))) : g.bandTop;
  return Math.max(CHIP_H / 2 + 1, top - LABEL_GAP_PX - CHIP_H / 2);
}

class GhostRenderer implements IPrimitivePaneRenderer {
  private readonly px: GhostPx | null;

  constructor(px: GhostPx | null) {
    this.px = px;
  }

  draw(target: CanvasRenderingTarget2D): void {
    const g = this.px;
    if (!g) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width;
      const right = Math.min(g.right, W);
      if (right <= g.left) return;
      ctx.save();
      ctx.beginPath();
      ctx.rect(g.left, 0, right - g.left, mediaSize.height);
      ctx.clip();
      for (const b of g.bars) {
        const top90 = Math.max(g.bandTop, b.y90);
        const top50 = Math.max(g.bandTop, b.y50);
        ctx.globalAlpha = AHEAD_DRAW.volumeWhisker;
        ctx.strokeStyle = AHEAD_DRAW.ai;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(b.x, top90);
        ctx.lineTo(b.x, Math.max(top90, b.y10));
        ctx.stroke();
        ctx.globalAlpha = AHEAD_DRAW.volumeFill;
        ctx.fillStyle = AHEAD_DRAW.ai;
        ctx.fillRect(b.x - g.barW / 2, top50, g.barW, b.yBase - top50);
        ctx.globalAlpha = 1;
        ctx.lineWidth = 1.2;
        ctx.strokeRect(b.x - g.barW / 2, top50, g.barW, b.yBase - top50);
        if (b.y90 < g.bandTop) {
          // Taller than the band: a caret at the top says the whisker goes on.
          ctx.beginPath();
          ctx.moveTo(b.x - CARET_PX, g.bandTop + CARET_PX);
          ctx.lineTo(b.x, g.bandTop);
          ctx.lineTo(b.x + CARET_PX, g.bandTop + CARET_PX);
          ctx.stroke();
        }
      }
      ctx.restore();
      if (g.label) {
        const w = chipWidth(ctx, g.label);
        chip(ctx, g.left + LABEL_INSET_PX, labelY(g, w), g.label, AHEAD_DRAW.aiText, AHEAD_DRAW.chipBg, 'start',
          { width: right, height: mediaSize.height });
      }
    });
  }
}

class GhostView implements IPrimitivePaneView {
  private readonly src: AheadVolumePrimitive;

  constructor(src: AheadVolumePrimitive) {
    this.src = src;
  }

  renderer(): IPrimitivePaneRenderer {
    return new GhostRenderer(this.src.px);
  }

  zOrder(): PrimitivePaneViewZOrder {
    return 'normal';
  }
}

export class AheadVolumePrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private scene: AheadScene | null = null;
  private label = '';
  private readonly views = [new GhostView(this)];
  px: GhostPx | null = null;

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
    this.chart = null;
    this.series = null;
    this.requestUpdate = null;
    this.px = null;
  }

  /** The scene, and the label over the ghost bars ("AI volume"). */
  setScene(scene: AheadScene | null, label: string): void {
    this.scene = scene;
    this.label = label;
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

  private layout(): GhostPx | null {
    const chart = this.chart;
    const series = this.series;
    const s = this.scene;
    if (!chart || !series || !s?.on || !s.ghostVolume?.length) return null;
    const step = stepper(chart, s.anchorT);
    const x0 = step?.x(0) ?? null;
    const xEnd = step?.x(s.horizon) ?? null;
    const yBase = series.priceToCoordinate(0);
    if (!step || x0 === null || xEnd === null || yBase === null) return null;
    const paneH = chart.paneSize().height;
    const margins = series.priceScale().options().scaleMargins;
    const bandTop = paneH * (margins?.top ?? 0);
    const bars: GhostBarPx[] = [];
    for (const g of s.ghostVolume) {
      const x = step.x(g.k);
      const [y10, y50, y90] = [g.q10, g.q50, g.q90].map(v => series.priceToCoordinate(v));
      if (x === null || y10 === null || y50 === null || y90 === null) continue;
      bars.push({ x, yBase, y10, y50, y90 });
    }
    return {
      left: x0 + step.half,
      right: xEnd + step.tail,
      bandTop,
      barW: Math.max(MIN_BAR_PX, 2 * step.half * GHOST_BAR_SHARE),
      bars,
      label: this.label,
    };
  }
}
