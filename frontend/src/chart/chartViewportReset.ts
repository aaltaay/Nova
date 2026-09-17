/**
 * "Reset Chart" -- put one pane's scales back where a fresh paint leaves them.
 * Reuses `defaultTimeScaleCommand` so a reset matches first paint, not a
 * live `setData` preserve.
 */
import type { IChartApi } from 'lightweight-charts';
import { applyTimeScaleCommand, defaultTimeScaleCommand } from './chartViewportPaint';

export function resetChartViewport(
  chart: IChartApi | null,
  timeframe: string,
  barCount: number,
): boolean {
  if (!chart) return false;
  try {
    chart.priceScale('right').applyOptions({ autoScale: true });
    applyTimeScaleCommand(chart, defaultTimeScaleCommand(timeframe, barCount));
    return true;
  } catch (err) {
    console.warn('chart reset: scales unavailable', timeframe, err);
    return false;
  }
}
