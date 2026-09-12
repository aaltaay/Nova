/**
 * "Reset Chart" -- put one pane's scales back where a fresh paint leaves them.
 * Reuses the same visible-range policy as `useChartBars.applyTimeScale`, so a
 * reset lands on the pinned intraday window instead of full history.
 */
import type { IChartApi } from 'lightweight-charts';
import { timeScaleRangeForSeries } from '../tickerChartData';

export function resetChartViewport(
  chart: IChartApi | null,
  timeframe: string,
  barCount: number,
): boolean {
  if (!chart) return false;
  try {
    chart.priceScale('right').applyOptions({ autoScale: true });
    const range = timeScaleRangeForSeries(timeframe, barCount);
    if (range) chart.timeScale().setVisibleLogicalRange(range);
    else chart.timeScale().fitContent();
    return true;
  } catch (err) {
    console.warn('chart reset: scales unavailable', timeframe, err);
    return false;
  }
}
