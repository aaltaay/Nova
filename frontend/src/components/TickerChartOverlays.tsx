/**
 * Price-pane overlays (EMAs + VWAP) on the main lightweight-charts instance.
 * Math comes from lightweight-charts-indicators — this only hosts LineSeries.
 */
import { useEffect, useRef } from 'react';
import {
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts';
import {
  CHART_EMA_COLORS,
  CHART_EMA_LENGTHS,
  CHART_VWAP_COLOR,
  type ChartEmaLength,
  type ChartIndicatorId,
} from '../constants';
import {
  computeEmaOverlays,
  computeVwapLine,
  type IndicatorBar,
} from '../chartIndicators';

interface Props {
  chart: IChartApi | null;
  bars: IndicatorBar[];
  enabled: ChartIndicatorId[];
}

type EmaSeriesMap = Partial<Record<ChartEmaLength, ISeriesApi<'Line'>>>;

export function TickerChartOverlays({ chart, bars, enabled }: Props) {
  const emaSeriesRef = useRef<EmaSeriesMap>({});
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  const showEmas = enabled.includes('emas');
  const showVwap = enabled.includes('vwap');

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

  // Push computed data into series
  useEffect(() => {
    if (!chart || bars.length === 0) return;

    if (showEmas) {
      const emas = computeEmaOverlays(bars);
      for (const length of CHART_EMA_LENGTHS) {
        const series = emaSeriesRef.current[length];
        if (series) series.setData(emas[length] as LineData<Time>[]);
      }
    }

    if (showVwap && vwapSeriesRef.current) {
      vwapSeriesRef.current.setData(computeVwapLine(bars) as LineData<Time>[]);
    }
  }, [chart, bars, showEmas, showVwap]);

  return null;
}
