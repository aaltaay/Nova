/**
 * Lightweight-charts series primitive: a small chip over the forming candle
 * counting down to its close (`barCountdown.ts` decides the value and where it
 * sits). Drawn on the pane's canvas, so it follows every scroll, zoom and
 * autoscale on the chart's own paint; the clock only asks for a repaint when
 * the digits change.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import {
  MismatchDirection,
  type IChartApi,
  type IPrimitivePaneRenderer,
  type IPrimitivePaneView,
  type ISeriesApi,
  type ISeriesPrimitive,
  type PrimitivePaneViewZOrder,
  type SeriesAttachedParameter,
  type SeriesType,
  type Time,
} from 'lightweight-charts';
import {
  barCountdown,
  barCountdownChipBox,
  type BarCountdown,
  type BarCountdownBar,
} from './barCountdown';
import {
  CHART_BAR_COUNTDOWN_BACK_COLOR,
  CHART_BAR_COUNTDOWN_BORDER_COLOR,
  CHART_BAR_COUNTDOWN_FONT,
  CHART_BAR_COUNTDOWN_RADIUS_PX,
  CHART_BAR_COUNTDOWN_TEXT_COLOR,
  CHART_BAR_COUNTDOWN_WARN_COLOR,
} from './barCountdownConstants';

export interface BarCountdownViewData {
  anchorX: number;
  wickTopY: number | null;
  wickBottomY: number | null;
  text: string;
  warn: boolean;
}

class BarCountdownRenderer implements IPrimitivePaneRenderer {
  private readonly _data: BarCountdownViewData | null;

  constructor(data: BarCountdownViewData | null) {
    this._data = data;
  }

  draw(target: CanvasRenderingTarget2D): void {
    const data = this._data;
    if (!data) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.save();
      ctx.font = CHART_BAR_COUNTDOWN_FONT;
      // Sized for "00:00", not the live digits, so the chip never twitches.
      const textWidth = ctx.measureText(data.text.replace(/\d/g, '0')).width;
      const box = barCountdownChipBox({
        anchorX: data.anchorX,
        wickTopY: data.wickTopY,
        wickBottomY: data.wickBottomY,
        textWidth,
        paneWidth: mediaSize.width,
        paneHeight: mediaSize.height,
      });
      if (box) {
        const x = Math.round(box.x) + 0.5;
        const y = Math.round(box.y) + 0.5;
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') {
          ctx.roundRect(x, y, box.width, box.height, CHART_BAR_COUNTDOWN_RADIUS_PX);
        } else {
          ctx.rect(x, y, box.width, box.height);
        }
        ctx.fillStyle = CHART_BAR_COUNTDOWN_BACK_COLOR;
        ctx.fill();
        ctx.lineWidth = 1;
        ctx.strokeStyle = data.warn ? CHART_BAR_COUNTDOWN_WARN_COLOR : CHART_BAR_COUNTDOWN_BORDER_COLOR;
        ctx.stroke();
        ctx.fillStyle = data.warn ? CHART_BAR_COUNTDOWN_WARN_COLOR : CHART_BAR_COUNTDOWN_TEXT_COLOR;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(data.text, x + box.width / 2, y + box.height / 2 + 0.5);
      }
      ctx.restore();
    });
  }
}

export class BarCountdownPaneView implements IPrimitivePaneView {
  private readonly _source: BarCountdownPrimitive;
  private _data: BarCountdownViewData | null = null;

  constructor(source: BarCountdownPrimitive) {
    this._source = source;
  }

  get data(): BarCountdownViewData | null {
    return this._data;
  }

  update(): void {
    this._data = null;
    const { chart, series } = this._source;
    if (!chart || !series) return;
    const last = this._source.lastBar();
    const countdown = this._source.countdown(last);
    if (!last || !countdown) return;
    const timeScale = chart.timeScale();
    const tipX = timeScale.timeToCoordinate(last.time);
    if (tipX === null) return;
    const tip = countdown.anchor === 'tip';
    this._data = {
      // No print yet this period: the candle forms in the slot after the tip.
      anchorX: tip ? tipX : tipX + timeScale.options().barSpacing,
      wickTopY: series.priceToCoordinate(tip ? last.high : last.close),
      wickBottomY: series.priceToCoordinate(tip ? last.low : last.close),
      text: countdown.text,
      warn: countdown.warn,
    };
  }

  renderer(): IPrimitivePaneRenderer {
    return new BarCountdownRenderer(this._data);
  }

  zOrder(): PrimitivePaneViewZOrder {
    return 'top';
  }
}

function isCandleRow(row: unknown): row is BarCountdownBar {
  if (!row || typeof row !== 'object') return false;
  const r = row as Record<string, unknown>;
  return typeof r.high === 'number' && typeof r.low === 'number' && typeof r.close === 'number';
}

export class BarCountdownPrimitive implements ISeriesPrimitive<Time> {
  private readonly _timeframe: string;
  private readonly _paneViews: BarCountdownPaneView[];
  private _chart: IChartApi | null = null;
  private _series: ISeriesApi<SeriesType> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _nowMs: number | null = null;
  /** What the last clock tick would show, so a tick repaints only when the digits change. */
  private _shown: string | null = null;

  constructor(timeframe: string) {
    this._timeframe = timeframe;
    this._paneViews = [new BarCountdownPaneView(this)];
  }

  get chart(): IChartApi | null {
    return this._chart;
  }

  get series(): ISeriesApi<SeriesType> | null {
    return this._series;
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
    this._requestUpdate();
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._shown = null;
  }

  updateAllViews(): void {
    for (const view of this._paneViews) view.update();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._paneViews;
  }

  /** The newest candle (a search, not a copy of every bar). */
  lastBar(): BarCountdownBar | null {
    const row = this._series?.dataByIndex(Number.MAX_SAFE_INTEGER, MismatchDirection.NearestLeft);
    return isCandleRow(row) ? row : null;
  }

  countdown(last: BarCountdownBar | null = this.lastBar()): BarCountdown | null {
    return barCountdown(this._nowMs, this._timeframe, last);
  }

  /** The venue's clock (epoch ms); null stops the countdown. */
  setNow(ms: number | null): void {
    this._nowMs = ms;
    const shown = this.countdown()?.text ?? null;
    if (shown === this._shown) return;
    this._shown = shown;
    this._requestUpdate?.();
  }
}
