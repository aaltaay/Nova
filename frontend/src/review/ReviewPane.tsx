/** One desk pane on the review route: the same chart, overlays and drawings, with bars handed in. */

import { useEffect, useMemo, useRef } from 'react';
import { LineStyle, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import { ChartKey } from '../stock_read';
import { TickerChartOscillatorPanes } from '../components/TickerChartOscillatorPanes';
import { TickerChartOverlays } from '../components/TickerChartOverlays';
import { useChartInstance, useChartSessionHighlight, useEphemeralDrawings } from '../chart';
import { rawBarsToIndicatorBars } from '../chartIndicators';
import { rawBarsToSeries, type RawBar } from '../tickerChartData';
import type { ChartIndicatorId } from '../constants';
import { sessionVisibleRange } from './reviewFit';
import { levelLines, type ReviewLevels } from './reviewLevels';
import { reviewKey } from './reviewKey';
import { TF_PANE, type ReviewTf } from './reviewQuery';
import type { ReviewPayload } from './reviewFixture';

interface Props {
  symbol: string;
  date: string;
  tf: ReviewTf;
  bars: RawBar[];
  vwapBars: RawBar[];
  levels: ReviewLevels;
  setups: ReviewPayload['setups'];
  enabled: ChartIndicatorId[];
  activeTool: string | null;
  clearToken: number;
  onPainted: () => void;
  onFocus: () => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
}

export function ReviewPane({
  symbol, date, tf, bars, vwapBars, levels, setups, enabled, activeTool, clearToken, onPainted, onFocus,
  onIndicatorToggle,
}: Props) {
  const pane = TF_PANE[tf];
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const paintedRef = useRef(onPainted);
  paintedRef.current = onPainted;
  const oscillators = enabled.filter((id): id is 'rsi' | 'macd' => id === 'rsi' || id === 'macd');
  const chartApi = useChartInstance({
    containerRef, chartRef, candleSeriesRef, volSeriesRef,
    chartHeight: 280, fillParentHeight: true, maximized: false, timeframe: pane.id, chartActive: true,
    oscillatorPaneCount: oscillators.length,
  });
  useChartSessionHighlight({ chartApi, candleSeriesRef, timeframe: pane.id, barsRevision: bars.length });
  useEphemeralDrawings({ containerRef, chartRef, candleSeriesRef, chartApi, activeTool, clearToken });

  const indicatorBars = useMemo(() => rawBarsToIndicatorBars(bars, pane.id), [bars, pane.id]);
  const vwapSource = useMemo(() => rawBarsToIndicatorBars(vwapBars, '1Min'), [vwapBars]);
  const lines = useMemo(() => levelLines(levels), [levels]);

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volSeriesRef.current;
    if (!chartApi || !chart || !candles || !volume) return;
    const series = rawBarsToSeries(bars, pane.id);
    candles.setData(series.candles);
    volume.setData(series.volumes);
    if (pane.id === '1Day') chart.timeScale().fitContent();
    else {
      try {
        chart.timeScale().setVisibleRange(sessionVisibleRange(date));
      } catch {
        chart.timeScale().fitContent();
      }
    }
    const frame = requestAnimationFrame(() => paintedRef.current());
    return () => cancelAnimationFrame(frame);
  }, [chartApi, bars, date, pane.id]);

  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chartApi || !series) return;
    const drawn = [
      ...lines.map((line) => series.createPriceLine({
        price: line.price, color: line.color, lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: line.title,
      })),
      ...setups.map((setup) => series.createPriceLine({
        price: setup.price, color: '#f59e0b', lineWidth: 1, lineStyle: LineStyle.Solid,
        axisLabelVisible: true, title: setup.label,
      })),
    ];
    return () => {
      for (const line of drawn) {
        try { series.removePriceLine(line); } catch { /* pane already gone */ }
      }
    };
  }, [chartApi, lines, setups]);

  return (
    <section className="chart-card review-pane" onPointerDown={onFocus} data-review-pane={pane.id}>
      <div className="review-pane__label">{pane.label}</div>
      <div ref={containerRef} className="chart-body review-pane__chart" />
      <TickerChartOverlays
        chart={chartApi}
        candleSeriesRef={candleSeriesRef}
        symbol={symbol}
        bars={indicatorBars}
        barsRevision={bars.length}
        enabled={enabled}
        timeframe={pane.id}
        vwapSourceBars={vwapSource}
        vwapSourceRevision={vwapSource.length}
        accountOverlay={false}
      />
      {oscillators.length > 0 && (
        <TickerChartOscillatorPanes
          parentChart={chartApi}
          bars={indicatorBars}
          barsRevision={bars.length}
          enabled={oscillators}
          onClose={(id) => onIndicatorToggle(id)}
        />
      )}
      <div className="review-pane__key">
        <ChartKey sections={reviewKey(tf, enabled, levels, setups.length)} testId={`review-key-${pane.id}`} />
      </div>
    </section>
  );
}
