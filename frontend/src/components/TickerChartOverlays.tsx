/**
 * Price-pane overlays (EMAs + VWAP) on the main lightweight-charts instance.
 * EMA math comes from lightweight-charts-indicators; VWAP comes from the
 * session-anchored series in `chart/vwapSession.ts`. Sub-minute panes splice
 * their own bars into that series so the line walks with painted candles
 * instead of stepping once per source minute. This file only hosts LineSeries.
 */
import { useEffect, useRef, type RefObject } from 'react';
import {
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts';
import { useChartPositionOverlay } from '../chart/useChartPositionOverlay';
import {
  CHART_EMA_COLORS,
  CHART_EMA_LENGTHS,
  CHART_VWAP_COLOR,
  type ChartEmaLength,
  type ChartIndicatorId,
} from '../constants';
import {
  computeEmaOverlays,
  vwapAxisTitleFromLine,
  type IndicatorBar,
} from '../chartIndicators';
import {
  coversSessionOpen,
  paneSessionBehindLabel,
  sampleVwapOntoBars,
  sessionVwapPoints,
  vwapSourceForPane,
} from '../chart/vwapSession';
import { isDailyTimeframe } from '../tickerChartData';

interface Props {
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  symbol: string;
  bars: IndicatorBar[];
  /** Stable revision from parent -- skip recompute when only identity changes. */
  barsRevision?: number;
  enabled: ChartIndicatorId[];
  timeframe: string;
  /** Shared 1Min bars the session VWAP is accumulated from. */
  vwapSourceBars?: IndicatorBar[];
  vwapSourceRevision?: number;
  vwapCoversOpen?: boolean;
  /** Live candle time ahead of the store -- VWAP must reach the painted tip. */
  liveTipTime?: number | null;
}

type EmaSeriesMap = Partial<Record<ChartEmaLength, ISeriesApi<'Line'>>>;

export function TickerChartOverlays({
  chart,
  candleSeriesRef,
  symbol,
  bars,
  barsRevision = 0,
  enabled,
  timeframe,
  vwapSourceBars = [],
  vwapSourceRevision = 0,
  vwapCoversOpen = true,
  liveTipTime = null,
}: Props) {
  const emaSeriesRef = useRef<EmaSeriesMap>({});
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lastPaintKeyRef = useRef<string>('');

  useChartPositionOverlay({
    chart,
    candleSeriesRef,
    symbol,
    timeframe,
    bars,
    barsRevision,
  });

  const showEmas = enabled.includes('emas');
  // A single-session VWAP means nothing on a daily+ chart, so it is not offered
  // there rather than drawing one hlc3 point per bar (which is what the old
  // per-pane cumulative indicator did).
  const showVwap = enabled.includes('vwap') && !isDailyTimeframe(timeframe);

  // Create / destroy EMA line series
  useEffect(() => {
    if (!chart) return;

    if (showEmas) {
      for (const length of CHART_EMA_LENGTHS) {
        if (emaSeriesRef.current[length]) continue;
        emaSeriesRef.current[length] = chart.addSeries(LineSeries, {
          color: CHART_EMA_COLORS[length],
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          title: `${length} EMA`,
        });
      }
    } else {
      for (const length of CHART_EMA_LENGTHS) {
        const series = emaSeriesRef.current[length];
        if (series) {
          chart.removeSeries(series);
          delete emaSeriesRef.current[length];
        }
      }
    }

    const emaSeries = emaSeriesRef.current;
    return () => {
      for (const length of CHART_EMA_LENGTHS) {
        const series = emaSeries[length];
        if (series && chart) {
          try {
            chart.removeSeries(series);
          } catch {
            /* chart already disposed */
          }
          delete emaSeries[length];
        }
      }
    };
  }, [chart, showEmas]);

  // Create / destroy VWAP line series
  useEffect(() => {
    if (!chart) return;

    if (showVwap) {
      if (!vwapSeriesRef.current) {
        vwapSeriesRef.current = chart.addSeries(LineSeries, {
          color: CHART_VWAP_COLOR,
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          title: 'VWAP',
        });
      }
    } else if (vwapSeriesRef.current) {
      chart.removeSeries(vwapSeriesRef.current);
      vwapSeriesRef.current = null;
    }

    return () => {
      if (vwapSeriesRef.current && chart) {
        try {
          chart.removeSeries(vwapSeriesRef.current);
        } catch {
          /* chart already disposed */
        }
        vwapSeriesRef.current = null;
      }
    };
  }, [chart, showVwap]);

  // Push computed data into series (skip when revision + toggles unchanged).
  useEffect(() => {
    if (!chart) return;
    if (bars.length === 0) {
      // Candles were cleared (replay window with no bars): drop the previous
      // session's lines too, or the pane shows EMAs/VWAP under "No bars".
      if (lastPaintKeyRef.current === '') return;
      lastPaintKeyRef.current = '';
      for (const length of CHART_EMA_LENGTHS) emaSeriesRef.current[length]?.setData([]);
      vwapSeriesRef.current?.setData([]);
      return;
    }
    const paintKey = [
      barsRevision, showEmas, showVwap, bars.length,
      vwapSourceRevision, vwapSourceBars.length, vwapCoversOpen,
      liveTipTime ?? '',
    ].join(':');
    if (lastPaintKeyRef.current === paintKey) return;
    lastPaintKeyRef.current = paintKey;

    if (showEmas) {
      const emas = computeEmaOverlays(bars);
      for (const length of CHART_EMA_LENGTHS) {
        const series = emaSeriesRef.current[length];
        if (series) series.setData(emas[length] as LineData<Time>[]);
      }
    }

    if (showVwap && vwapSeriesRef.current) {
      const sourceBars = vwapSourceForPane(vwapSourceBars, bars, timeframe);
      const line = sampleVwapOntoBars(
        sessionVwapPoints(sourceBars),
        bars,
        timeframe,
        { extendToTime: liveTipTime ?? undefined },
      );
      vwapSeriesRef.current.setData(line);
      const title = vwapAxisTitleFromLine(
        line,
        sourceBars.length > 0 ? !coversSessionOpen(sourceBars) : !vwapCoversOpen,
      );
      // A pane still on an earlier session names it (QA R28).
      const behind = paneSessionBehindLabel(vwapSourceBars, bars);
      vwapSeriesRef.current.applyOptions({ title: behind ? `${title} · ${behind}` : title });
    }
  }, [
    chart, bars, barsRevision, showEmas, showVwap, timeframe,
    vwapSourceBars, vwapSourceRevision, vwapCoversOpen, liveTipTime,
  ]);

  return null;
}
