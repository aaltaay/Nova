/**
 * "Reset Chart" -- put one pane's scales back where a fresh paint leaves them.
 * Reuses `defaultTimeScaleCommand` so a reset matches first paint, not a
 * live `setData` preserve, and hands the view back to Nova (`operatorView.ts`).
 */
import type { IChartApi } from 'lightweight-charts';
import { applyTimeScaleCommand, defaultTimeScaleCommand } from './chartViewportPaint';
import { releaseView } from './operatorView';

export function resetChartViewport(
  chart: IChartApi | null,
  timeframe: string,
  barCount: number,
): boolean {
  if (!chart) return false;
  try {
    chart.priceScale('right').applyOptions({ autoScale: true });
    applyTimeScaleCommand(chart, defaultTimeScaleCommand(timeframe, barCount));
    releaseView(chart);
    return true;
  } catch (err) {
    console.warn('chart reset: scales unavailable', timeframe, err);
    return false;
  }
}
