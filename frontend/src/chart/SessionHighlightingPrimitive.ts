/**
 * Lightweight-charts series primitive — shades each bar's vertical strip by
 * market session (premarket / RTH / after-hours). Pattern follows TradingView's
 * session-highlighting plugin example, inlined so we own the highlighter.
 *
 * A tick colours only what it changed and asks for no redraw: the series' own
 * update already redraws the pane, and lightweight-charts refreshes this view on
 * every redraw. `requestUpdate` is a *full* redraw, which lays out the whole page
 * (the price axis sets a canvas font); calling it on every tick, as the plugin
 * example does, cost the Trader tab most of its frame rate.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import {
  MismatchDirection,
  type Coordinate,
  type DataChangedScope,
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
import { sessionColorForChartTime } from './sessionHighlight';

interface BandPoint {
  x: Coordinate | number;
  color: string;
}

interface ViewData {
  data: BandPoint[];
  barWidth: number;
}

class SessionHighlightPaneRenderer implements IPrimitivePaneRenderer {
  private readonly _viewData: ViewData;

  constructor(data: ViewData) {
    this._viewData = data;
  }

  draw(target: CanvasRenderingTarget2D): void {
    const points = this._viewData.data;
    target.useBitmapCoordinateSpace(scope => {
      const ctx = scope.context;
      const height = scope.bitmapSize.height;
      const halfWidth = (scope.horizontalPixelRatio * this._viewData.barWidth) / 2;
      const cutOff = -1 * (halfWidth + 1);
      const maxX = scope.bitmapSize.width;
      for (const point of points) {
        const xScaled = Number(point.x) * scope.horizontalPixelRatio;
        if (xScaled < cutOff) continue;
        ctx.fillStyle = point.color;
        const x1 = Math.max(0, Math.round(xScaled - halfWidth));
        const x2 = Math.min(maxX, Math.round(xScaled + halfWidth));
        ctx.fillRect(x1, 0, Math.max(0, x2 - x1), height);
      }
    });
  }
}

class SessionHighlightPaneView implements IPrimitivePaneView {
  private readonly _source: SessionHighlightingPrimitive;
  private _data: ViewData = { data: [], barWidth: 6 };

  constructor(source: SessionHighlightingPrimitive) {
    this._source = source;
  }

  update(): void {
    const chart = this._source.chart;
    if (!chart) {
      this._data = { data: [], barWidth: 6 };
      return;
    }
    const timeScale = chart.timeScale();
    const mapped = this._source.backgroundColors.map(d => ({
      x: timeScale.timeToCoordinate(d.time) ?? -100,
      color: d.color,
    }));
    let barWidth = 6;
    if (mapped.length > 1) {
      const delta = Number(mapped[1].x) - Number(mapped[0].x);
      if (Number.isFinite(delta) && Math.abs(delta) > 0.5) {
        barWidth = Math.abs(delta);
      }
    }
    this._data = { data: mapped, barWidth };
  }

  renderer(): IPrimitivePaneRenderer {
    return new SessionHighlightPaneRenderer(this._data);
  }

  zOrder(): PrimitivePaneViewZOrder {
    return 'bottom';
  }
}

interface BackgroundColor {
  time: Time;
  color: string;
}

/** The same bars, so the same colours: a colour follows from its bar's time alone. */
function sameBars(a: readonly BackgroundColor[], b: readonly BackgroundColor[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) if (a[i].time !== b[i].time) return false;
  return true;
}

export class SessionHighlightingPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApi | null = null;
  private _series: ISeriesApi<SeriesType> | null = null;
  private _requestUpdate: (() => void) | null = null;
  private _paneViews: SessionHighlightPaneView[];
  private _backgroundColors: BackgroundColor[] = [];
  private readonly _onDataChanged = (scope: DataChangedScope) => {
    if (scope !== 'update' || !this._appendLastBar()) this._rebuildColors();
  };

  constructor() {
    this._paneViews = [new SessionHighlightPaneView(this)];
  }

  get chart(): IChartApi | null {
    return this._chart;
  }

  get backgroundColors(): readonly BackgroundColor[] {
    return this._backgroundColors;
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
    this._series.subscribeDataChanged(this._onDataChanged);
    this._rebuildColors();
    this._requestUpdate();
  }

  detached(): void {
    this._series?.unsubscribeDataChanged(this._onDataChanged);
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._backgroundColors = [];
  }

  updateAllViews(): void {
    for (const view of this._paneViews) view.update();
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._paneViews;
  }

  /** Call after setData so colors rebuild even if the library coalesces events; redraws only when they changed. */
  refresh(): void {
    const before = this._backgroundColors;
    this._rebuildColors();
    if (!sameBars(before, this._backgroundColors)) this._requestUpdate?.();
  }

  /**
   * A tick moves the last bar or adds one after it: colour the new bar only. False when the
   * last bar is not where the colours end -- the data changed some other way; rebuild them all.
   */
  private _appendLastBar(): boolean {
    const series = this._series;
    if (!series) return false;
    const last = series.dataByIndex(Number.MAX_SAFE_INTEGER, MismatchDirection.NearestLeft);
    const known = this._backgroundColors[this._backgroundColors.length - 1];
    if (!last || !known || typeof last.time !== 'number' || typeof known.time !== 'number') return false;
    if (last.time === known.time) return true;
    if (last.time < known.time) return false;
    this._backgroundColors = [
      ...this._backgroundColors,
      { time: last.time, color: sessionColorForChartTime(last.time) },
    ];
    return true;
  }

  private _rebuildColors(): void {
    const series = this._series;
    if (!series) {
      this._backgroundColors = [];
      return;
    }
    this._backgroundColors = series.data().map(point => ({
      time: point.time,
      color: sessionColorForChartTime(point.time),
    }));
  }
}
