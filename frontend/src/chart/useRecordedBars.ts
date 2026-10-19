/** Paint a recorded feed once. No fetch, no timer, no Sim listener, no mock candles. */

import { useEffect, useMemo, useRef, type RefObject } from 'react';
import type { CandlestickData, IChartApi, ISeriesApi, Time } from 'lightweight-charts';
import { rawBarsToIndicatorBars, type IndicatorBar } from '../chartIndicators';
import { timeframeSeconds, type RawBar } from '../tickerChartData';
import { paintBars } from './chartBarsPaint';
import type { RecordedChartFeed } from './chartFeed';

export function recordedBarsClosedBy(bars: RawBar[], timeframe: string, asOfIso: string): RawBar[] {
  if (timeframe === '1Day' || timeframe === '1Week') {
    const day = asOfIso.slice(0, 10);
    return bars.filter((bar) => bar.t.slice(0, 10) <= day);
  }
  const asOf = Date.parse(asOfIso);
  const step = timeframeSeconds(timeframe) * 1000;
  if (!Number.isFinite(asOf) || step <= 0) return [];
  return bars.filter((bar) => {
    const start = Date.parse(bar.t);
    return Number.isFinite(start) && start + step <= asOf;
  });
}

export function useRecordedBars({
  feed,
  timeframe,
  chartRef,
  candleSeriesRef,
  volSeriesRef,
  chartApi,
  onPainted,
}: {
  feed: RecordedChartFeed;
  timeframe: string;
  chartRef: RefObject<IChartApi | null>;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  volSeriesRef: RefObject<ISeriesApi<'Histogram'> | null>;
  chartApi: IChartApi | null;
  onPainted?: () => void;
}): { indicatorBars: IndicatorBar[]; barsRevision: number } {
  const closed = useMemo(
    () => recordedBarsClosedBy(feed.bars[timeframe as '1Min'] ?? [], timeframe, feed.asOfIso),
    [feed, timeframe],
  );
  const indicatorBars = useMemo(
    () => rawBarsToIndicatorBars(closed, timeframe),
    [closed, timeframe],
  );
  const lastCandleRef = useRef<CandlestickData<Time> | null>(null);
  const epoch = useRef({ current: 0 });
  const prev = useRef<RawBar[] | null>(null);
  const painted = useRef(onPainted);
  painted.current = onPainted;

  useEffect(() => {
    if (!chartApi || !candleSeriesRef.current || !volSeriesRef.current) return;
    paintBars(closed, timeframe, candleSeriesRef, volSeriesRef, lastCandleRef, chartRef, prev.current, epoch.current);
    prev.current = closed;
    painted.current?.();
  }, [chartApi, chartRef, candleSeriesRef, volSeriesRef, closed, timeframe]);

  const barsRevision =
    indicatorBars.length +
    (typeof indicatorBars[0]?.time === 'number' ? indicatorBars[0].time : 0) +
    (typeof indicatorBars[indicatorBars.length - 1]?.time === 'number'
      ? (indicatorBars[indicatorBars.length - 1].time as number)
      : 0);

  return { indicatorBars, barsRevision };
}
