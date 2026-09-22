import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
} from 'lightweight-charts';
import { removeChartAfterCleanups } from '../chart/chartDispose';
import {
  CHART_INDICATOR_PANE_HEIGHT,
  CHART_OSCILLATOR_CLOSE_TITLE,
  type ChartOscillatorId,
} from '../constants';
import {
  computeMacdPane,
  computeRsiPane,
  type IndicatorBar,
} from '../chartIndicators';
import { shouldPaintOscillator } from '../chart/oscillatorPaint';
import {
  formatChartCrosshairTime,
  formatChartTickMark,
} from '../chart/chartTimeFormat';
import { chartRightPriceScaleOptions } from '../chart/chartPriceScale';

interface Props {
  parentChart: IChartApi | null;
  bars: IndicatorBar[];
  barsRevision?: number;
  enabled: ChartOscillatorId[];
  /** Per-pane "x" -- turns the oscillator off without hunting for a toolbar. */
  onClose?: (id: ChartOscillatorId) => void;
}

/**
 * Separate oscillator panes (RSI / MACD) synced to the main price chart.
 * Math comes from lightweight-charts-indicators — this only hosts + syncs panes.
 */
export function TickerChartOscillatorPanes({
  parentChart,
  bars,
  barsRevision = 0,
  enabled,
  onClose,
}: Props) {
  return (
    <div className="chart-oscillators" data-testid="chart-oscillators">
      {enabled.includes('rsi') && (
        <OscillatorPane
          label="RSI"
          parentChart={parentChart}
          bars={bars}
          barsRevision={barsRevision}
          kind="rsi"
          onClose={onClose}
        />
      )}
      {enabled.includes('macd') && (
        <OscillatorPane
          label="MACD"
          parentChart={parentChart}
          bars={bars}
          barsRevision={barsRevision}
          kind="macd"
          onClose={onClose}
        />
      )}
    </div>
  );
}

function OscillatorPane({
  label,
  parentChart,
  bars,
  barsRevision,
  kind,
  onClose,
}: {
  label: string;
  parentChart: IChartApi | null;
  bars: IndicatorBar[];
  barsRevision: number;
  kind: 'rsi' | 'macd';
  onClose?: (id: ChartOscillatorId) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineARef = useRef<ISeriesApi<'Line'> | null>(null);
  const lineBRef = useRef<ISeriesApi<'Line'> | null>(null);
  const histRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const syncingRef = useRef(false);
  const lastPaintKeyRef = useRef('');
  const [seriesGen, setSeriesGen] = useState(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialH = container.clientHeight || CHART_INDICATOR_PANE_HEIGHT;
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
      rightPriceScale: chartRightPriceScaleOptions(),
      width: container.clientWidth,
      height: initialH || CHART_INDICATOR_PANE_HEIGHT,
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
    lastPaintKeyRef.current = '';
    setSeriesGen(g => g + 1);

    // Never resize a removed pane: toggling RSI / MACD rebuilt the chart while
    // the old one's first-frame resize was still queued (QA V19).
    let disposed = false;
    const ro = new ResizeObserver(() => {
      if (disposed || !containerRef.current) return;
      const el = containerRef.current;
      const h = el.clientHeight || CHART_INDICATOR_PANE_HEIGHT;
      chart.applyOptions({ width: el.clientWidth, height: h });
    });
    ro.observe(container);
    // Apply once after layout so grid CSS height (not createChart default) wins.
    const firstFrame = requestAnimationFrame(() => {
      if (disposed || !containerRef.current || chartRef.current !== chart) return;
      const el = containerRef.current;
      chart.applyOptions({
        width: el.clientWidth,
        height: el.clientHeight || CHART_INDICATOR_PANE_HEIGHT,
      });
    });

    return () => {
      disposed = true;
      cancelAnimationFrame(firstFrame);
      ro.disconnect();
      removeChartAfterCleanups(chart);
      chartRef.current = null;
      lineARef.current = null;
      lineBRef.current = null;
      histRef.current = null;
      lastPaintKeyRef.current = '';
    };
  }, [kind]);

  useEffect(() => {
    const seriesReady =
      kind === 'rsi'
        ? Boolean(lineARef.current)
        : Boolean(histRef.current && lineARef.current && lineBRef.current);
    const paintKey = `${seriesGen}:${barsRevision}:${kind}:${bars.length}`;
    if (!shouldPaintOscillator(seriesReady, lastPaintKeyRef.current, paintKey)) return;
    if (kind === 'rsi') {
      const data = computeRsiPane(bars);
      lineARef.current?.setData(data.rsi);
    } else {
      const data = computeMacdPane(bars);
      histRef.current?.setData(data.histogram);
      lineARef.current?.setData(data.macd);
      lineBRef.current?.setData(data.signal);
    }
    lastPaintKeyRef.current = paintKey;
    // setData resets the child window to last-N. Follow the price chart --
    // never copy that stub range back up (that zoomed 5Min/1Min onto the tip).
    const parentRange = parentChart?.timeScale().getVisibleLogicalRange();
    if (parentRange && chartRef.current) {
      syncingRef.current = true;
      chartRef.current.timeScale().setVisibleLogicalRange(parentRange);
      syncingRef.current = false;
    }
  }, [bars, barsRevision, kind, seriesGen, parentChart]);

  useEffect(() => {
    const child = chartRef.current;
    if (!parentChart || !child) return;

    const syncFromParent = (range: LogicalRange | null) => {
      if (!range || syncingRef.current) return;
      syncingRef.current = true;
      child.timeScale().setVisibleLogicalRange(range);
      syncingRef.current = false;
    };

    parentChart.timeScale().subscribeVisibleLogicalRangeChange(syncFromParent);

    const current = parentChart.timeScale().getVisibleLogicalRange();
    if (current) child.timeScale().setVisibleLogicalRange(current);

    return () => {
      parentChart.timeScale().unsubscribeVisibleLogicalRangeChange(syncFromParent);
    };
  }, [parentChart, kind]);

  return (
    <div className="chart-oscillator-pane" data-testid={`chart-oscillator-${kind}`}>
      <span className="chart-oscillator-label">
        {label}
        {onClose && (
          <button
            type="button"
            className="chart-oscillator-close"
            title={CHART_OSCILLATOR_CLOSE_TITLE}
            aria-label={`Hide ${label}`}
            data-testid={`chart-oscillator-close-${kind}`}
            onClick={() => onClose(kind)}
          >
            ×
          </button>
        )}
      </span>
      <div className="chart-oscillator-body" ref={containerRef} />
    </div>
  );
}
