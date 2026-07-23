import { useEffect, useRef } from 'react';
import {
  createChart,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
} from 'lightweight-charts';
import {
  CHART_INDICATOR_PANE_HEIGHT,
  type ChartOscillatorId,
} from '../constants';
import {
  computeMacdPane,
  computeRsiPane,
  type IndicatorBar,
} from '../chartIndicators';
import {
  formatChartCrosshairTime,
  formatChartTickMark,
} from '../chart/chartTimeFormat';

interface Props {
  parentChart: IChartApi | null;
  bars: IndicatorBar[];
  enabled: ChartOscillatorId[];
}

/**
 * Separate oscillator panes (RSI / MACD) synced to the main price chart.
 * Math comes from lightweight-charts-indicators — this only hosts + syncs panes.
 */
export function TickerChartOscillatorPanes({ parentChart, bars, enabled }: Props) {
  return (
    <div className="chart-oscillators">
      {enabled.includes('rsi') && (
        <OscillatorPane
          label="RSI"
          parentChart={parentChart}
          bars={bars}
          kind="rsi"
        />
      )}
      {enabled.includes('macd') && (
        <OscillatorPane
          label="MACD"
          parentChart={parentChart}
          bars={bars}
          kind="macd"
        />
      )}
    </div>
  );
}

function OscillatorPane({
  label,
  parentChart,
  bars,
  kind,
}: {
  label: string;
  parentChart: IChartApi | null;
  bars: IndicatorBar[];
  kind: 'rsi' | 'macd';
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineARef = useRef<ISeriesApi<'Line'> | null>(null);
  const lineBRef = useRef<ISeriesApi<'Line'> | null>(null);
  const histRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const syncingRef = useRef(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: { background: { color: '#161921' }, textColor: '#8b92a5' },
      grid: { vertLines: { color: '#262a36' }, horzLines: { color: '#262a36' } },
      crosshair: {
        vertLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
        horzLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
      },
      localization: {
        locale: 'en-US',
        timeFormatter: formatChartCrosshairTime,
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#262a36',
        visible: false,
        tickMarkFormatter: formatChartTickMark,
      },
      rightPriceScale: { borderColor: '#262a36' },
      width: container.clientWidth,
      height: CHART_INDICATOR_PANE_HEIGHT,
    });

    if (kind === 'rsi') {
      lineARef.current = chart.addSeries(LineSeries, {
        color: '#7E57C2',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      // Standard RSI reference levels
      lineARef.current.createPriceLine({ price: 70, color: 'rgba(239,68,68,0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
      lineARef.current.createPriceLine({ price: 30, color: 'rgba(16,185,129,0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false });
    } else {
      histRef.current = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'price', precision: 4, minMove: 0.0001 },
        priceLineVisible: false,
        lastValueVisible: false,
      });
      lineARef.current = chart.addSeries(LineSeries, {
        color: '#2962FF',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      lineBRef.current = chart.addSeries(LineSeries, {
        color: '#FF6D00',
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
      });
    }

    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return;
      chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      lineARef.current = null;
      lineBRef.current = null;
      histRef.current = null;
    };
  }, [kind]);

  useEffect(() => {
    if (kind === 'rsi') {
      const data = computeRsiPane(bars);
      lineARef.current?.setData(data.rsi);
    } else {
      const data = computeMacdPane(bars);
      histRef.current?.setData(data.histogram);
      lineARef.current?.setData(data.macd);
      lineBRef.current?.setData(data.signal);
    }
  }, [bars, kind]);

  useEffect(() => {
    const child = chartRef.current;
    if (!parentChart || !child) return;

    const syncFromParent = (range: LogicalRange | null) => {
      if (!range || syncingRef.current) return;
      syncingRef.current = true;
      child.timeScale().setVisibleLogicalRange(range);
      syncingRef.current = false;
    };
    const syncFromChild = (range: LogicalRange | null) => {
      if (!range || syncingRef.current) return;
      syncingRef.current = true;
      parentChart.timeScale().setVisibleLogicalRange(range);
      syncingRef.current = false;
    };

    parentChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromParent);
    child.timeScale().subscribeVisibleLogicalRangeChange(syncFromChild);

    const current = parentChart.timeScale().getVisibleLogicalRange();
    if (current) child.timeScale().setVisibleLogicalRange(current);

    return () => {
      parentChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncFromParent);
      child.timeScale().unsubscribeVisibleLogicalRangeChange(syncFromChild);
    };
  }, [parentChart, kind]);

  return (
    <div className="chart-oscillator-pane">
      <span className="chart-oscillator-label">{label}</span>
      <div className="chart-oscillator-body" ref={containerRef} />
    </div>
  );
}
