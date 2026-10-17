/**
 * Draws the volume profiles on the 5-minute pane (plan §6.1).
 * - Today's: a blue box from its anchor to the axis, its value area shaded, the POC in red, and its histogram in a lane
 *   right of the last candle.
 * - Yesterday's regular session: a grey box, its histogram growing right from its 16:00 close, and its value area
 *   carried into today as dashed lines.
 * A white outline traces each histogram so a P, b, D or thin shape reads at a glance. Under the candles go the boxes,
 * bands and lines; over them the histograms, outlines, tabs and the anchor's handle.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
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
import type { VolumeProfile } from './volumeProfile';
import {
  VP_COLORS,
  VP_LABEL_FONT,
  VP_LANE_GAP_PX,
  VP_LANE_MAX_PX,
  VP_LANE_MIN_PX,
  VP_LANE_SHARE,
  VP_OUTLINE_SMOOTH_ROWS,
  VP_OVERLAY_ALPHA_SCALE,
  VP_ROW_ALPHA_IN,
  VP_ROW_ALPHA_OUT,
  VP_TAG_FONT,
  VP_YESTERDAY_ALPHA_IN,
  VP_YESTERDAY_ALPHA_OUT,
  VP_YESTERDAY_LANE_MAX_PX,
  vpAnchorLabel,
} from './volumeProfileConstants';

const BAR_SEC = 300;

export interface ProfileLayer {
  profile: VolumeProfile;
  /** Chart seconds (ET wall clock read as UTC) where the measured stretch starts and ends. */
  start: number;
  end: number;
  title: string;
}

export interface ProfileScene {
  /** `anchor` is the handle's clock, e.g. "09:30". */
  today: (ProfileLayer & { anchor: string }) | null;
  yesterday: ProfileLayer | null;
  /** Px at the axis kept for the pane's tag column; today's lane ends left of it. */
  rightInset: number;
  /** Why a profile is not drawn, in the backend's words. */
  notes: string[];
}

export interface HandleRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface LayerGeometry {
  layer: ProfileLayer;
  left: number;
  end: number;
  yHigh: number;
  yLow: number;
  yPoc: number;
  yVah: number;
  yVal: number;
  rowTop: number[];
  rowBottom: number[];
}

interface Geometry {
  today: (LayerGeometry & { anchor: string }) | null;
  yesterday: LayerGeometry | null;
  rightInset: number;
  /** The last candle's right edge (px). */
  lastRight: number;
  notes: string[];
}

const EMPTY: Geometry = { today: null, yesterday: null, rightInset: 0, lastRight: 0, notes: [] };

function smoothed(rows: number[], k: number): number[] {
  return rows.map((_, i) => {
    let sum = 0;
    let n = 0;
    for (let j = Math.max(0, i - k); j <= Math.min(rows.length - 1, i + k); j += 1) {
      sum += rows[j];
      n += 1;
    }
    return sum / n;
  });
}

function tag(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, align: 'left' | 'right' | 'center', bg: string): HandleRect {
  ctx.font = VP_TAG_FONT;
  const w = ctx.measureText(text).width + 12;
  const h = 15;
  const left = align === 'left' ? x : align === 'right' ? x - w : x - w / 2;
  ctx.fillStyle = bg;
  ctx.beginPath();
  ctx.roundRect(left, y, w, h, 3);
  ctx.fill();
  ctx.fillStyle = VP_COLORS.label;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillText(text, left + 6, y + h / 2 + 0.5);
  return { x: left, y, w, h };
}

function hLine(ctx: CanvasRenderingContext2D, y: number, x0: number, x1: number, color: string, width: number, dash: number[] = []): void {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.beginPath();
  ctx.moveTo(x0, Math.round(y) + 0.5);
  ctx.lineTo(x1, Math.round(y) + 0.5);
  ctx.stroke();
  ctx.setLineDash([]);
}

/** A level's name at the start of its line, on a backing so a candle never covers it. */
function levelName(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, color: string): void {
  ctx.font = VP_LABEL_FONT;
  const w = ctx.measureText(text).width;
  ctx.fillStyle = VP_COLORS.labelBacking;
  ctx.beginPath();
  ctx.roundRect(x - 3, y - 14, w + 6, 12, 2);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  ctx.fillText(text, x, y - 3);
}

/** One histogram: rows grow from `base` toward `dir` (-1 left, +1 right), up volume next to the base. */
function histogram(ctx: CanvasRenderingContext2D, g: LayerGeometry, base: number, dir: 1 | -1, width: number, alphaIn: number, alphaOut: number): void {
  const p = g.layer.profile;
  const totals = p.up.map((u, i) => u + p.down[i]);
  const max = Math.max(...totals);
  if (max <= 0) return;
  for (let i = 0; i < totals.length; i += 1) {
    const top = g.rowTop[i];
    const h = Math.max(1, g.rowBottom[i] - top);
    const wUp = (p.up[i] / max) * width;
    const wDown = (p.down[i] / max) * width;
    ctx.globalAlpha = i >= p.valRow && i <= p.vahRow ? alphaIn : alphaOut;
    ctx.fillStyle = VP_COLORS.up;
    ctx.fillRect(dir < 0 ? base - wUp : base, top, wUp, h);
    ctx.fillStyle = VP_COLORS.down;
    ctx.fillRect(dir < 0 ? base - wUp - wDown : base + wUp, top, wDown, h);
  }
  ctx.globalAlpha = 1;
  const s = smoothed(totals, VP_OUTLINE_SMOOTH_ROWS);
  ctx.strokeStyle = VP_COLORS.outline;
  ctx.lineWidth = 1;
  ctx.beginPath();
  s.forEach((v, i) => {
    const x = base + dir * (v / max) * width;
    const y = (g.rowTop[i] + g.rowBottom[i]) / 2;
    if (i === 0) ctx.moveTo(x, g.rowBottom[i]);
    ctx.lineTo(x, y);
  });
  ctx.lineTo(base + dir * (s[s.length - 1] / max) * width, g.rowTop[s.length - 1]);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
  ctx.beginPath();
  ctx.moveTo(base, g.yHigh);
  ctx.lineTo(base, g.yLow);
  ctx.stroke();
}

class ProfileRenderer implements IPrimitivePaneRenderer {
  private readonly g: Geometry;
  private readonly layer: 'under' | 'over';
  private readonly onHandle: (r: HandleRect | null) => void;

  constructor(g: Geometry, layer: 'under' | 'over', onHandle: (r: HandleRect | null) => void) {
    this.g = g;
    this.layer = layer;
    this.onHandle = onHandle;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width;
      const H = mediaSize.height;
      const { today, yesterday, rightInset, lastRight } = this.g;
      const free = W - 1 - rightInset - (lastRight + VP_LANE_GAP_PX);
      const fits = free >= VP_LANE_MIN_PX;
      const laneW = fits ? Math.min(VP_LANE_MAX_PX, W * VP_LANE_SHARE, free) : Math.min(VP_LANE_MAX_PX, W * VP_LANE_SHARE);
      const yLaneW = yesterday
        ? Math.max(0, Math.min(VP_YESTERDAY_LANE_MAX_PX, (today ? today.left : W) - yesterday.end - 24))
        : 0;
      if (this.layer === 'under') {
        if (yesterday) this.yesterdayUnder(ctx, yesterday, yLaneW, W);
        if (today) this.todayUnder(ctx, today, W, H);
        return;
      }
      if (yesterday) this.yesterdayOver(ctx, yesterday, yLaneW);
      if (today) this.todayOver(ctx, today, W, H, laneW, rightInset, fits ? 1 : VP_OVERLAY_ALPHA_SCALE);
      else this.onHandle(null);
      this.g.notes.forEach((note, i) => {
        ctx.font = VP_TAG_FONT;
        const w = ctx.measureText(note).width + 10;
        const x = W - rightInset - 6 - w;
        const y = H - 44 - i * 17;
        ctx.fillStyle = VP_COLORS.labelBacking;
        ctx.fillRect(x, y, w, 14);
        ctx.fillStyle = VP_COLORS.yesterday;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(note, x + 5, y + 7.5);
      });
    });
  }

  private yesterdayUnder(ctx: CanvasRenderingContext2D, g: LayerGeometry, laneW: number, W: number): void {
    const left = Math.max(0, g.left);
    const right = g.end + laneW;
    if (right <= 0) return;
    ctx.fillStyle = VP_COLORS.yesterdayTint;
    ctx.fillRect(left, g.yHigh, right - left, g.yLow - g.yHigh);
    ctx.fillStyle = VP_COLORS.yesterdayValueBand;
    ctx.fillRect(left, g.yVah, right - left, g.yVal - g.yVah);
    ctx.strokeStyle = VP_COLORS.yesterdayFrame;
    ctx.lineWidth = 1;
    ctx.strokeRect(Math.round(left) + 0.5, Math.round(g.yHigh) + 0.5, Math.round(right - left), Math.round(g.yLow - g.yHigh));
    // Yesterday's value area and POC run on into today.
    for (const y of [g.yVah, g.yPoc, g.yVal]) hLine(ctx, y, left, W, 'rgba(142,142,147,0.75)', 1, [5, 4]);
  }

  private yesterdayOver(ctx: CanvasRenderingContext2D, g: LayerGeometry, laneW: number): void {
    if (laneW > 8) histogram(ctx, g, g.end, 1, laneW - 4, VP_YESTERDAY_ALPHA_IN, VP_YESTERDAY_ALPHA_OUT);
    const tagX = g.end + laneW + 6;
    levelName(ctx, 'yVAH', tagX, g.yVah, VP_COLORS.yesterday);
    levelName(ctx, 'yPOC', tagX, g.yPoc, VP_COLORS.yesterday);
    levelName(ctx, 'yVAL', tagX, g.yVal, VP_COLORS.yesterday);
    const tabY = g.yHigh - 17 >= 2 ? g.yHigh - 17 : g.yHigh + 3;
    tag(ctx, g.layer.title, g.end + laneW, tabY, 'right', 'rgba(99,99,102,0.92)');
  }

  private todayUnder(ctx: CanvasRenderingContext2D, g: LayerGeometry, W: number, H: number): void {
    const left = Math.max(0, g.left);
    ctx.fillStyle = VP_COLORS.todayTint;
    ctx.fillRect(left, g.yHigh, W - left, g.yLow - g.yHigh);
    ctx.fillStyle = VP_COLORS.todayValueBand;
    ctx.fillRect(left, g.yVah, W - left, g.yVal - g.yVah);
    ctx.strokeStyle = VP_COLORS.todayFrame;
    ctx.lineWidth = 1;
    ctx.strokeRect(Math.round(left) + 0.5, Math.round(g.yHigh) + 0.5, Math.round(W - left) - 1, Math.round(g.yLow - g.yHigh));
    hLine(ctx, g.yVah, left, W, VP_COLORS.value, 1);
    hLine(ctx, g.yVal, left, W, VP_COLORS.value, 1);
    const pocH = Math.max(2, g.rowBottom[g.layer.profile.pocRow] - g.rowTop[g.layer.profile.pocRow]);
    ctx.fillStyle = 'rgba(255,69,58,0.28)';
    ctx.fillRect(left, g.yPoc - pocH / 2 - 1, W - left, pocH + 2);
    hLine(ctx, g.yPoc, left, W, VP_COLORS.poc, 1.5);
    if (g.left >= 0) {
      ctx.strokeStyle = VP_COLORS.value;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(Math.round(g.left) + 0.5, g.yHigh);
      ctx.lineTo(Math.round(g.left) + 0.5, H);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  private todayOver(
    ctx: CanvasRenderingContext2D, g: LayerGeometry & { anchor: string }, W: number, H: number, laneW: number, inset: number,
    fade: number,
  ): void {
    histogram(ctx, g, W - 1 - inset, -1, laneW - 6, VP_ROW_ALPHA_IN * fade, VP_ROW_ALPHA_OUT * fade);
    const left = Math.max(0, g.left);
    levelName(ctx, 'VAH', left + 5, g.yVah, VP_COLORS.value);
    levelName(ctx, 'POC', left + 5, g.yPoc, VP_COLORS.poc);
    levelName(ctx, 'VAL', left + 5, g.yVal, VP_COLORS.value);
    const tabY = g.yHigh - 17 >= 2 ? g.yHigh - 17 : g.yHigh + 3;
    tag(ctx, g.layer.title, W - 2, tabY, 'right', 'rgba(10,132,255,0.92)');
    this.onHandle(g.left >= 0 ? tag(ctx, vpAnchorLabel(g.anchor), g.left, H - 20, 'center', 'rgba(10,132,255,0.95)') : null);
  }
}

class ProfilePaneView implements IPrimitivePaneView {
  private readonly source: VolumeProfilePrimitive;
  private readonly layer: 'under' | 'over';

  constructor(source: VolumeProfilePrimitive, layer: 'under' | 'over') {
    this.source = source;
    this.layer = layer;
  }

  update(): void {}

  renderer(): IPrimitivePaneRenderer {
    return new ProfileRenderer(this.source.geometry(), this.layer, (r) => this.source.setHandle(r));
  }

  zOrder(): PrimitivePaneViewZOrder {
    return this.layer === 'under' ? 'bottom' : 'normal';
  }
}

export class VolumeProfilePrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApi | null = null;
  private _series: ISeriesApi<SeriesType> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _times: number[] = [];
  private _scene: ProfileScene = { today: null, yesterday: null, rightInset: 0, notes: [] };
  private _geometry: Geometry = EMPTY;
  private _handle: HandleRect | null = null;
  private readonly _views = [new ProfilePaneView(this, 'under'), new ProfilePaneView(this, 'over')];
  private readonly _onData = () => {
    this._times = (this._series?.data() ?? []).map((d) => Number(d.time));
  };

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
    this._series.subscribeDataChanged(this._onData);
    this._onData();
  }

  detached(): void {
    this._series?.unsubscribeDataChanged(this._onData);
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._handle = null;
  }

  setScene(scene: ProfileScene): void {
    this._scene = scene;
    this._requestUpdate?.();
  }

  /** The anchor handle where it was last drawn, in the pane's CSS pixels. */
  handle(): HandleRect | null {
    return this._handle;
  }

  setHandle(rect: HandleRect | null): void {
    this._handle = rect;
  }

  geometry(): Geometry {
    return this._geometry;
  }

  /** The bar time nearest a pane x, from the candles the pane holds now. */
  timeAt(x: number): number | null {
    const chart = this._chart;
    const n = this._times.length;
    if (!chart || n === 0) return null;
    const logical = chart.timeScale().coordinateToLogical(x);
    if (logical == null) return null;
    return this._times[Math.min(n - 1, Math.max(0, Math.round(logical)))];
  }

  updateAllViews(): void {
    this._geometry = this._layout();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._views;
  }

  /** A chart time's x, between bars and past the last one too. */
  private _xAt(t: number): number | null {
    const chart = this._chart;
    const times = this._times;
    const n = times.length;
    if (!chart || n === 0) return null;
    let lo = 0;
    let hi = n;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (times[mid] < t) lo = mid + 1;
      else hi = mid;
    }
    let logical: number;
    if (lo === n) logical = n - 1 + (t - times[n - 1]) / BAR_SEC;
    else if (times[lo] === t) logical = lo;
    else if (lo === 0) logical = -(times[0] - t) / BAR_SEC;
    else logical = lo - 1 + (t - times[lo - 1]) / (times[lo] - times[lo - 1]);
    return chart.timeScale().logicalToCoordinate(logical as Logical);
  }

  private _layer(layer: ProfileLayer | null, half: number): LayerGeometry | null {
    const series = this._series;
    if (!layer || !series) return null;
    const p = layer.profile;
    const y = (price: number) => series.priceToCoordinate(price);
    const left = this._xAt(layer.start);
    const end = this._xAt(layer.end);
    const ys = [y(p.high), y(p.low), y(p.poc), y(p.vah), y(p.val)];
    if (left == null || end == null || ys.some((v) => v == null)) return null;
    const [yHigh, yLow, yPoc, yVah, yVal] = ys as number[];
    const rowTop = p.up.map((_, i) => y(p.low + (i + 1) * p.rowSize) ?? yHigh);
    const rowBottom = p.up.map((_, i) => y(p.low + i * p.rowSize) ?? yLow);
    return { layer, left: left - half, end: end - half, yHigh, yLow, yPoc, yVah, yVal, rowTop, rowBottom };
  }

  private _layout(): Geometry {
    if (!this._chart) return EMPTY;
    const ts = this._chart.timeScale();
    const half = ts.options().barSpacing / 2;
    const today = this._layer(this._scene.today, half);
    const lastX = this._times.length ? ts.logicalToCoordinate((this._times.length - 1) as Logical) : null;
    return {
      today: today && this._scene.today ? { ...today, anchor: this._scene.today.anchor } : null,
      yesterday: this._layer(this._scene.yesterday, half),
      rightInset: this._scene.rightInset,
      lastRight: (lastX ?? 0) + half,
      notes: this._scene.notes,
    };
  }
}
