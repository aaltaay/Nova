/** One desk pane on the review route: the same chart, overlays and drawings, with bars handed in. */

import { useEffect, useMemo, useRef } from 'react';
import { LineStyle, TickMarkType, type AutoscaleInfo, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts';
import { formatChartTickMark } from '../chart';
import { ChartKey } from '../stock_read';
import { TickerChartOscillatorPanes } from '../components/TickerChartOscillatorPanes';
import { TickerChartOverlays } from '../components/TickerChartOverlays';
import { useChartInstance, useChartSessionHighlight, useEphemeralDrawings } from '../chart';
import { rawBarsToIndicatorBars } from '../chartIndicators';
import { rawBarsToSeries, type RawBar } from '../tickerChartData';
import type { ChartIndicatorId } from '../constants';
import { levelLines, packPriceLines, type ReviewLevels } from './reviewLevels';
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
  /** Gallery cells are short. The price pane stays larger than MACD. */
  compact?: boolean;
}

export function ReviewPane({
  symbol, date, tf, bars, vwapBars, levels, setups, enabled, activeTool, clearToken, onPainted, onFocus,
  onIndicatorToggle,
  compact = false,
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
  const span = useMemo(() => {
    if (!bars.length) return 1;
    const high = Math.max(...bars.map((bar) => bar.h));
    const low = Math.min(...bars.map((bar) => bar.l));
    return Math.max(high - low, 0.01);
  }, [bars]);
  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volSeriesRef.current;
    if (!chartApi || !chart || !candles || !volume) return;
    const series = rawBarsToSeries(bars, pane.id);
    candles.setData(series.candles);
    volume.setData(series.volumes);
    volume.applyOptions({ lastValueVisible: false, priceLineVisible: false });
    if (pane.id === '1Day') {
      candles.applyOptions({
        autoscaleInfoProvider: (original: () => AutoscaleInfo | null): AutoscaleInfo | null => {
          const info = original();
          if (!info?.priceRange) return info;
          const minValue = Math.max(0, info.priceRange.minValue);
          return {
            priceRange: { minValue, maxValue: Math.max(info.priceRange.maxValue, minValue) },
            margins: { above: 0.08, below: 0 },
          };
        },
      });
      chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.08, bottom: 0 } });
    }
    if (compact) chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.22, bottom: 0.06 } });
    // setVisibleRange clamps to the first bar, so "4:00 AM" sits on the left edge and is cut.
    // Empty bars on the left move that label inward. Daily gets the same treatment on the right.
    chart.timeScale().fitContent();
    const logical = chart.timeScale().getVisibleLogicalRange();
    if (logical) {
      const left = pane.id === '1Min' ? 36 : pane.id === '5Min' ? 14 : pane.id === '10Sec' ? 80 : 3;
      const right = pane.id === '1Day' ? 14 : 6;
      chart.timeScale().setVisibleLogicalRange({ from: logical.from - left, to: logical.to + right });
    }
    chart.applyOptions({
      timeScale: {
        tickMarkFormatter: (time: Time, tickMarkType: TickMarkType, locale: string) => {
          const x = chart.timeScale().timeToCoordinate(time);
          if (x != null && x < 54) return '';
          return formatChartTickMark(time, tickMarkType, locale, pane.id === '10Sec') ?? '';
        },
      },
    });
    containerRef.current?.setAttribute('data-review-fit', 'logical');
    containerRef.current?.setAttribute('data-review-date', date);
    const frame = requestAnimationFrame(() => paintedRef.current());
    return () => cancelAnimationFrame(frame);
  }, [chartApi, bars, date, pane.id, compact]);

  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chartApi || !series) return;
    const plot = containerRef.current?.clientHeight || (compact ? 220 : 400);
    const packed = packPriceLines(
      [
        ...levelLines(levels),
        ...setups.map((setup) => ({ title: setup.label, price: setup.price, color: '#f59e0b' })),
      ],
      (22 / plot) * span,
    );
    const drawn = packed.map((line) => series.createPriceLine({
      price: line.price, color: line.color, lineWidth: 1,
      lineStyle: line.color === '#f59e0b' ? LineStyle.Solid : LineStyle.Dashed,
      axisLabelVisible: true, title: line.title,
    }));
    return () => {
      for (const line of drawn) {
        try { series.removePriceLine(line); } catch { /* pane already gone */ }
      }
    };
  }, [chartApi, levels, setups, span, compact]);

  return (
    <section
      className={`chart-card review-pane${compact ? ' review-pane--compact' : ''}`}
      onPointerDown={onFocus}
      data-review-pane={pane.id}
    >
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
