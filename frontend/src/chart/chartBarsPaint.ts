import type {
  CandlestickData,
  IChartApi,
  ISeriesApi,
  Time,
} from 'lightweight-charts';
import {
  rawBarsToIndicatorBars,
  type IndicatorBar,
} from '../chartIndicators';
import {
  canIncrementalBarsUpdate,
  rawBarsToSeries,
  type RawBar,
} from '../tickerChartData';
import {
  applyTimeScaleCommand,
  paintTimeScaleCommand,
  snapshotChartViewport,
  type ChartViewportSnapshot,
} from './chartViewportPaint';

export interface ChartSeriesRefs {
  chartRef: React.RefObject<IChartApi | null>;
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>;
  volSeriesRef: React.RefObject<ISeriesApi<'Histogram'> | null>;
  lastCandleRef: React.RefObject<CandlestickData<Time> | null>;
}

export interface PaintBarsResult {
  indicators: IndicatorBar[];
  tipOnly: boolean;
  skipIndicatorCommit: boolean;
}

/** Same-length tip change: series.update is enough; skip indicator rebuild. */
export function shouldSkipIndicatorBarsCommit(
  prev: RawBar[] | null,
  next: RawBar[],
): boolean {
  if (prev == null || prev.length === 0 || next.length === 0) return false;
  if (prev.length !== next.length) return false;
  return canIncrementalBarsUpdate(prev, next);
}

export function paintFull(
  candles: CandlestickData<Time>[],
  volumes: ReturnType<typeof rawBarsToSeries>['volumes'],
  candleSeriesRef: ChartSeriesRefs['candleSeriesRef'],
  volSeriesRef: ChartSeriesRefs['volSeriesRef'],
  chartRef: ChartSeriesRefs['chartRef'],
  timeframe: string,
  snapshot: ChartViewportSnapshot | null,
  paintEpoch: { current: number },
): void {
  const epoch = ++paintEpoch.current;
  candleSeriesRef.current?.setData(candles);
  volSeriesRef.current?.setData(volumes);
  const seriesTime = candles.length > 0
    ? { from: candles[0].time, to: candles[candles.length - 1].time }
    : null;
  const command = paintTimeScaleCommand(timeframe, candles.length, snapshot, seriesTime);
  applyTimeScaleCommand(chartRef.current, command);
  if (typeof requestAnimationFrame !== 'function') return;
  requestAnimationFrame(() => {
    if (paintEpoch.current !== epoch) return;
    applyTimeScaleCommand(chartRef.current, command);
  });
}

export function paintBars(
  bars: RawBar[],
  tf: string,
  candleSeriesRef: ChartSeriesRefs['candleSeriesRef'],
  volSeriesRef: ChartSeriesRefs['volSeriesRef'],
  lastCandleRef: ChartSeriesRefs['lastCandleRef'],
  chartRef: ChartSeriesRefs['chartRef'],
  prevBars: RawBar[] | null,
  paintEpoch: { current: number },
  /**
   * Viewport captured before the series was cleared -- a transient empty
   * refresh, or a Paper / Live / Sim switch re-sourcing the pane. Without it
   * the next paint sees `prevBars === []` or `null`, snapshots a chart with no
   * bars (which reports null), and is mistaken for a first paint -- i.e.
   * fitContent, i.e. the operator's zoom thrown away.
   */
  viewportOverride: ChartViewportSnapshot | null = null,
): PaintBarsResult {
  const { candles, volumes } = rawBarsToSeries(bars, tf);
  const snapshot = viewportOverride
    ?? (prevBars == null
      ? null
      : snapshotChartViewport(chartRef.current, prevBars.length));
  const canIncremental =
    prevBars != null
    && canIncrementalBarsUpdate(prevBars, bars)
    && candleSeriesRef.current
    && volSeriesRef.current
    && candles.length > 0;
  const skipIndicatorCommit = shouldSkipIndicatorBarsCommit(prevBars, bars);

  if (canIncremental) {
    const tip = candles[candles.length - 1];
    const tipVol = volumes[volumes.length - 1];
    try {
      candleSeriesRef.current!.update(tip);
      volSeriesRef.current!.update(tipVol);
    } catch {
      paintFull(
        candles, volumes, candleSeriesRef, volSeriesRef, chartRef, tf, snapshot, paintEpoch,
      );
      lastCandleRef.current = candles.length > 0 ? candles[candles.length - 1] : null;
      return {
        indicators: rawBarsToIndicatorBars(bars, tf),
        tipOnly: false,
        skipIndicatorCommit: false,
      };
    }
  } else {
    paintFull(
      candles, volumes, candleSeriesRef, volSeriesRef, chartRef, tf, snapshot, paintEpoch,
    );
  }
  lastCandleRef.current = candles.length > 0 ? candles[candles.length - 1] : null;
  if (skipIndicatorCommit) {
    return { indicators: [], tipOnly: true, skipIndicatorCommit: true };
  }
  return {
    indicators: rawBarsToIndicatorBars(bars, tf),
    tipOnly: Boolean(canIncremental),
    skipIndicatorCommit: false,
  };
}
